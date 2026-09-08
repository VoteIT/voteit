import itertools
import json
import os
from time import sleep

from locust.clients import HttpSession
from requests.cookies import RequestsCookieJar
from websocket import WebSocket
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
USER_PASSWORD = _require_env("USER_PASSWORD")
USER_COUNT = int(os.getenv("USER_COUNT", "50"))
LOGIN_URL = "/admin/login/"
#: Bounds every ws recv. A refused subscribe answers with channel.subscribe_error
#: and never a state_complete, and a stopped RQ worker answers with nothing at
#: all -- without a timeout either one wedges the user instead of reporting.
WS_TIMEOUT = 10


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


# TODO: Measure performance and errors.
# Look at https://github.com/locustio/locust/blob/master/locust/contrib/socketio.py for inspiration
class SocketUser(VoteitUser):
    weight = 3
    ws: WebSocket = None

    @task
    def subscribe_meeting(self):
        # "participants" is what a non-moderator client subscribes to; it now
        # carries the meeting-wide state the separate "meeting" channel used to.
        payload = {"pk": MEETING_ID, "channel_type": "participants"}
        self.ws.send(json.dumps({"action": "channel.subscribe", "payload": payload}))
        # The initial state now arrives as a stream terminated by
        # channel.state_complete, rather than inside the subscribed frame.
        self._drain_state("participants")
        sleep(1)
        self.ws.send(json.dumps({"action": "channel.leave", "payload": payload}))

    def _drain_state(self, channel_type: str, limit: int = 200):
        """Read frames until this channel's initial state is done.

        Returns on channel.subscribe_error too: a refusal never sends a
        state_complete, so waiting for one would only burn the frame limit and
        then the socket timeout. Frames for other channels are skipped rather
        than counted as the answer -- the meeting stream is not the only one in
        flight.
        """
        for _ in range(limit):
            frame = json.loads(self.ws.recv())
            if (frame.get("payload") or {}).get("channel_type") != channel_type:
                continue
            if frame.get("action") in (
                "channel.state_complete",
                "channel.subscribe_error",
            ):
                return
        raise RuntimeError(f"No state_complete for {channel_type} in {limit} frames")

    def on_start(self):
        super().on_start()
        cookies = get_cookie_string(self.client.cookies)
        # Replace http* -> ws* (https* -> wss*) and add path.
        socket_url = f"ws{self.host[4:]}/ws/"
        self.ws = create_connection(
            socket_url,
            cookie=cookies,
            timeout=WS_TIMEOUT,
            # AllowedHostsOriginValidator drops a handshake whose Origin is not
            # in ALLOWED_HOSTS, which is only "*" in development.
            origin=self.host,
        )
        # The consumer pushes s.versions and then a whole subscribe stream for
        # the user's organisation channel without being asked. Left buffered,
        # the first subscribe_meeting would return on *this* stream's
        # state_complete and every measurement after it would be one behind.
        self._drain_state("organisation")

    def on_stop(self):
        if self.ws:
            self.ws.close()
