import itertools
import json
import os
from contextlib import suppress
from time import monotonic

from locust.clients import HttpSession
from requests.cookies import RequestsCookieJar
from websocket import WebSocket
from websocket import WebSocketException
from websocket import WebSocketTimeoutException
from websocket import create_connection

from locust import HttpUser
from locust import between
from locust import task


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Must supply env {name}")
    return value


HOST = os.getenv("HOST", "http://voteit.localhost:8000")
MEETING_ID = int(_require_env("MEETING_ID"))
AGENDA_ITEM_ID = int(_require_env("AGENDA_ITEM_ID"))
USER_PASSWORD = _require_env("USER_PASSWORD")
USER_COUNT = int(os.getenv("USER_COUNT", "50"))
LOGIN_URL = "/admin/login/"
#: Bounds every ws recv. A refused subscribe answers with channel.subscribe_error
#: and never a state_complete, and a stopped RQ worker answers with nothing at
#: all -- without a timeout either one wedges the user instead of reporting.
WS_TIMEOUT = 10
#: The two frames that end a subscribe stream, one way or the other.
STATE_COMPLETE = "channel.state_complete"
SUBSCRIBE_ERROR = "channel.subscribe_error"
#: Seconds to stay subscribed, reading, before leaving again. A real client
#: holds its subscription and receives pushes; it does not subscribe and
#: immediately walk away. This is also what keeps the socket alive -- see
#: SocketUser._pump.
SUBSCRIPTION_HOLD = float(os.getenv("SUBSCRIPTION_HOLD", "27"))


def do_login(_id: int, client: HttpSession):
    client.get(LOGIN_URL)
    # CSRF_USE_SESSIONS is off, so the cookie carries a valid form token and we
    # do not have to scrape the login page for one.
    csrf_token = client.cookies.get("csrftoken")
    if not csrf_token:
        raise RuntimeError(f"No csrftoken cookie from GET {LOGIN_URL}")
    # Do not follow the redirect: a success is a 302 to LOGIN_REDIRECT_URL ("/"),
    # which is the SPA's route and nothing this test wants to measure or count.
    response = client.post(
        url=LOGIN_URL,
        data={
            "csrfmiddlewaretoken": csrf_token,
            "password": USER_PASSWORD,
            "username": f"user-{_id}",
        },
        headers={"Referer": client.base_url + LOGIN_URL},  # Django requires Referer
        name=LOGIN_URL,
        allow_redirects=False,
    )
    if response.status_code != 302 or not client.cookies.get("sessionid"):
        # A bad password or a non-staff user just re-renders the form with a 200.
        # Without this the whole run proceeds anonymously and measures 403s.
        raise RuntimeError(f"Login as user-{_id} failed: HTTP {response.status_code}")


class VoteitUser(HttpUser):
    """Shared login. Locust skips abstract classes when picking user classes."""

    abstract = True
    wait_time = between(1.5, 15)
    host = HOST
    user_id: int

    _id_counter = itertools.count()

    def on_start(self):
        self.user_id = self._next_user_id()
        do_login(self.user_id, self.client)
        user_response = self.client.get("/api/user/")
        assert user_response.status_code == 200, user_response.status_code

    def _next_user_id(self) -> int:
        # Every worker of a distributed run counts from zero, so without the
        # offset they would all drive user-0 in lockstep.
        worker_index = getattr(self.environment.runner, "worker_index", 0)
        return (worker_index + next(self._id_counter)) % USER_COUNT


class LoggedInApiUser(VoteitUser):
    @task
    def organisation(self):
        # Singular: the router prefix is "organisation", and its list() resolves
        # the org from the request host, so HOST must be the tenant's host.
        self.client.get("/api/organisation/")

    @task
    def meetings(self):
        self.client.get("/api/meetings/")

    @task
    def roles(self):
        # The filter field is "context", not "meeting" -- and it is a
        # RequiredModelChoiceFilter, so a name it does not know returns an empty
        # list with a 200 rather than an error.
        self.client.get(
            f"/api/meeting-roles/?context={MEETING_ID}",
            name="/api/meeting-roles/?context=[id]",
        )

    @task
    def er(self):
        self.client.get(
            f"/api/electoral-registers/?meeting={MEETING_ID}",
            name="/api/electoral-registers/?meeting=[id]",
        )

    @task
    def er_policies(self):
        self.client.get("/api/electoral-register-policies/")

    @task
    def user(self):
        self.client.get("/api/user/")


def get_cookie_string(cookies: RequestsCookieJar) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())


class SocketUser(VoteitUser):
    # Short, because the pacing now lives inside the task: a cycle is dominated
    # by SUBSCRIPTION_HOLD seconds spent subscribed and listening. With two
    # tasks that still comes to roughly one subscribe per channel per minute,
    # but the socket is being read throughout instead of lying idle.
    wait_time = between(1, 5)
    ws: WebSocket = None

    @task
    def subscribe_meeting(self):
        # "participants" is what a non-moderator client subscribes to; it now
        # carries the meeting-wide state the separate "meeting" channel used to.
        self._subscribe_cycle(MEETING_ID, "participants")

    @task
    def subscribe_agenda_item(self):
        # Proposals, discussion posts and their metadata. The agenda items
        # themselves travel on participants/moderators, not here.
        self._subscribe_cycle(AGENDA_ITEM_ID, "agenda_item")

    def _subscribe_cycle(self, pk: int, channel_type: str):
        """Subscribe, wait for the initial state, then leave again.

        Reported to locust as one request: the response time is the round trip
        from channel.subscribe to channel.state_complete, which is what a real
        client waits through before it can show anything, and the length is the
        state that arrived.
        """
        if self.ws is None:
            self._connect()
        if self.ws is None:  # the connect failed and has already been reported
            return
        payload = {"pk": pk, "channel_type": channel_type}
        with self.environment.events.request.measure(
            "WS", f"subscribe {channel_type}"
        ) as meta:
            try:
                self.ws.send(
                    json.dumps({"action": "channel.subscribe", "payload": payload})
                )
                # The initial state now arrives as a stream terminated by
                # channel.state_complete, rather than inside the subscribed frame.
                action, meta["response_length"] = self._drain_state(channel_type)
                if action == SUBSCRIBE_ERROR:
                    # A refusal is a fast, cheap answer. Left unraised it would
                    # be indistinguishable from a subscribe that worked, and the
                    # fastest rows in the table would be the broken ones.
                    raise RuntimeError(f"refused: {channel_type} {pk}")
            except (WebSocketException, OSError):
                # A socket that timed out mid-frame is desynced, not merely
                # idle: every later send and recv on it raises too, and
                # on_stop's close() raises on top of that. measure() records
                # this exception and swallows it, so the socket has to be
                # dropped here or the next task would inherit the wreckage.
                self._disconnect()
                raise
        if meta["exception"] is not None:
            return
        # Stay subscribed and keep reading, the way a real client does.
        try:
            self._pump(SUBSCRIPTION_HOLD)
            self.ws.send(json.dumps({"action": "channel.leave", "payload": payload}))
        except (WebSocketException, OSError) as error:
            self._disconnect()
            # Not measured as a timing -- the duration would just be
            # SUBSCRIPTION_HOLD every time and would swamp the percentiles --
            # but a socket dying mid-hold is exactly what we want to see, so it
            # is reported as a failure with no timing attached.
            self.environment.events.request.fire(
                request_type="WS",
                name=f"hold {channel_type}",
                response_time=0,
                response_length=0,
                exception=error,
                context={},
            )

    def _pump(self, seconds: float) -> None:
        """Read and discard frames for a while, keeping the socket answered.

        websocket-client replies to the server's PING only from inside recv():
        there is no background thread, so a socket nobody reads never sends a
        PONG. Staging's daphne pings every 10s (--ping-interval 10) and autobahn
        drops the connection 30s after an unanswered one, which is why an idle
        user used to lose its socket and then raise BrokenPipeError on the next
        send. Reading here also consumes what the server pushes to a subscriber,
        which is traffic a real client handles and this test otherwise ignores.
        """
        deadline = monotonic() + seconds
        try:
            while (remaining := deadline - monotonic()) > 0:
                self.ws.settimeout(min(remaining, WS_TIMEOUT))
                try:
                    self.ws.recv()
                except WebSocketTimeoutException:
                    # Nothing arrived in the window, which is the normal case on
                    # a quiet meeting. The timeout lands between frames rather
                    # than inside one, so the stream stays in step.
                    pass
        finally:
            self.ws.settimeout(WS_TIMEOUT)

    def _drain_state(self, channel_type: str, limit: int = 200) -> tuple[str, int]:
        """Read frames until this channel's initial state is done.

        Returns the action that ended the stream and the size of the JSON read
        along the way, for the caller to report. Ends on channel.subscribe_error
        too: a refusal never sends a state_complete, so waiting for one would
        only burn the frame limit and then the socket timeout. Frames for other
        channels are skipped rather than counted as the answer -- the meeting
        stream is not the only one in flight.
        """
        received = 0
        for _ in range(limit):
            raw = self.ws.recv()
            received += len(raw)
            frame = json.loads(raw)
            if (frame.get("payload") or {}).get("channel_type") != channel_type:
                continue
            action = frame.get("action")
            if action in (STATE_COMPLETE, SUBSCRIBE_ERROR):
                return action, received
        raise RuntimeError(f"No state_complete for {channel_type} in {limit} frames")

    def on_start(self):
        super().on_start()
        self._connect()

    def _connect(self):
        """Open the socket. Measured: the handshake is not free either.

        The time covers the organisation stream the server pushes unasked, so
        it is comparable to a subscribe rather than to a bare TCP connect.
        """
        cookies = get_cookie_string(self.client.cookies)
        # Replace http* -> ws* (https* -> wss*) and add path.
        socket_url = f"ws{self.host[4:]}/ws/"
        with self.environment.events.request.measure("WS", "connect") as meta:
            try:
                self.ws = create_connection(
                    socket_url,
                    cookie=cookies,
                    timeout=WS_TIMEOUT,
                    # AllowedHostsOriginValidator drops a handshake whose Origin
                    # is not in ALLOWED_HOSTS, which is only "*" in development.
                    origin=self.host,
                )
                # The consumer pushes s.versions and then a whole subscribe
                # stream for the user's organisation channel without being
                # asked. Left buffered, the first subscribe_meeting would return
                # on *this* stream's state_complete and every measurement after
                # it would be one behind.
                _, meta["response_length"] = self._drain_state("organisation")
            except (WebSocketException, OSError):
                self._disconnect()
                raise

    def _disconnect(self):
        if self.ws is not None:
            # Closing a socket that is already gone raises; that exception says
            # nothing the failure that got us here has not already said.
            with suppress(WebSocketException, OSError):
                self.ws.close()
            self.ws = None

    def on_stop(self):
        self._disconnect()
