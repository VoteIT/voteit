# Load testing

Locust drives the REST API and the websocket consumer against a running dev or
staging server. `locustfile.py` defines two user classes: `LoggedInApiUser` hits
a spread of read endpoints, and `SocketUser` (weight 3) connects to `/ws/` and
subscribes to a meeting's `participants` channel.

## Setup

```bash
uv sync --group locust
```

## Fixtures

The load test logs in as `user-0 … user-(N-1)`, which the `testing_meeting`
command creates along with an ongoing meeting, an agenda item and seven
proposals:

```bash
python manage.py testing_meeting <org_id> <password> -u 20
```

It prints the two pks you need, as `Meeting:` and `AI:`. The users are created with
`is_staff=True`, which is what lets them log in through `/admin/login/` — the
only username+password form in the project (everything else is OAuth).

**The command blocks on `input()` and deletes the meeting and users when you
press enter**, so leave it running for the whole load test.

## Running

```bash
HOST=http://voteit.localhost:8000 \
MEETING_ID=<pk> \
AGENDA_ITEM_ID=<pk> \
USER_PASSWORD=<password> \
USER_COUNT=20 \
uv run --group locust locust -f locust/locustfile.py
```

Then open the web UI, or add `--headless -u 10 -r 2 -t 60s` for a scripted run.

| env | default | notes |
| --- | --- | --- |
| `HOST` | `http://voteit.localhost:8000` | Must be the tenant host: `/api/organisation/` resolves the org from it and 401s on a mismatch. `--host` on the command line overrides it. |
| `MEETING_ID` | required | Printed by `testing_meeting` as `Meeting:`. |
| `AGENDA_ITEM_ID` | required | Printed by `testing_meeting` as `AI:`. Used by the `agenda_item` subscribe task. |
| `USER_PASSWORD` | required | The password argument given to `testing_meeting`. |
| `USER_COUNT` | `50` | Must match `-u` on `testing_meeting`, or logins fail for users that were never created. |

## Requirements on the server

- **An RQ worker on the `default` queue.** `channel.subscribe` is enqueued, not
  handled inline — with no worker the socket never answers and `SocketUser`
  fails on the 10s websocket timeout.
- **The host in `ALLOWED_HOSTS`.** `AllowedHostsOriginValidator` rejects the
  websocket handshake by `Origin`. Development sets `["*"]`; staging builds the
  list from the `HOST` env var.
