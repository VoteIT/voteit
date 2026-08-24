import itertools
import json
import os
import re
from threading import Event
from time import sleep

from locust import HttpUser, task, between
from locust.clients import HttpSession
from requests.cookies import RequestsCookieJar
from websocket import create_connection, WebSocket

# from dotenv import load_dotenv

# load_dotenv()

MEETING_ID = int(os.getenv("MEETING_ID"))
assert MEETING_ID, "Must supply env MEETING_ID"
USER_PASSWORD = os.getenv("USER_PASSWORD")
assert USER_PASSWORD, "Must supply env USER_PASSWORD"
USER_COUNT = int(os.getenv("USER_COUNT", 50))


def find_csrf_token(body: str):
    for part in body.split():
        if res := re.match(r'^value="(\w+)">$', part):
            return res[1]


def do_login(_id: int, client: HttpSession):
    response = client.get("/admin/")
    # Extrahera CSRF-token från svar
    csrf_token = find_csrf_token(response.text)
    url = response.request.url
    client.post(
        url=url,
        data={
            "csrfmiddlewaretoken": csrf_token,
            "password": USER_PASSWORD,
            "username": f"user-{_id}",
        },
        headers={"Referer": url},  # Django kräver Referer-header
    )


class LoggedInApiUser(HttpUser):
    wait_time = between(1.5, 15)
    host = os.getenv("HOST", "http://voteit.localhost:8000")
    user_id: int

    _id_counter = itertools.count()

    @task
    def organisations(self):
        self.client.get("/api/organisations/")

    @task
    def meetings(self):
        self.client.get("/api/meetings/")

    @task
    def roles(self):
        self.client.get(f"/api/meeting-roles/?meeting={MEETING_ID}")

    @task
    def er(self):
        self.client.get(f"/api/electoral-registers/?meeting={MEETING_ID}")

    @task
    def er_policies(self):
        self.client.get("/api/electoral-register-policies/")

    @task
    def user(self):
        self.client.get("/api/user/")

    def on_start(self):
        self.user_id = next(self._id_counter) % USER_COUNT
        do_login(self.user_id, self.client)
        user_response = self.client.get("/api/user/")
        assert user_response.status_code == 200


def get_cookie_string(cookies: RequestsCookieJar) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())


# TODO: Measure performance and errors.
# Look at https://github.com/locustio/locust/blob/master/locust/contrib/socketio.py for inspiration
class SocketUser(HttpUser):
    wait_time = between(1.5, 15)
    weight = 3
    ws: WebSocket = None
    event: Event
    host = os.getenv("HOST", "http://voteit.localhost:8000")
    user_id: int

    _id_counter = itertools.count()

    @task
    def subscribe_meeting(self):
        # "participants" is what a non-moderator client subscribes to; it now
        # carries the meeting-wide state the separate "meeting" channel used to.
        payload = {"pk": MEETING_ID, "channel_type": "participants"}
        self.ws.send(json.dumps({"action": "channel.subscribe", "payload": payload}))
        # The initial state now arrives as a stream terminated by
        # channel.state_complete, rather than inside the subscribed frame.
        self._drain_until("channel.state_complete")
        sleep(1)
        self.ws.send(json.dumps({"action": "channel.leave", "payload": payload}))

    def _drain_until(self, action: str, limit: int = 200):
        """Read frames until the given action arrives, or we give up."""
        for _ in range(limit):
            try:
                frame = json.loads(self.ws.recv())
            except Exception:
                return
            if frame.get("action") == action:
                return

    def on_start(self):
        self.user_id = next(self._id_counter) % USER_COUNT
        do_login(self.user_id, self.client)
        cookies = get_cookie_string(self.client.cookies)
        # Replace http* -> ws* (https* -> wss*) and add path.
        socket_url = f"ws{self.host[4:]}/ws/"
        self.ws = create_connection(socket_url, cookie=cookies)

    def on_stop(self):
        if self.ws:
            self.ws.close()
