# voteit.messaging

Owns the websocket layer: the consumer, the message registry, batching, the
channel definitions and the `Connection` model. Built on
[chanx](https://pypi.org/project/chanx/) over Django Channels.

## Wire format

`{"action": "<name>", "payload": {...}}` in both directions. The socket is
**push-only** apart from `channel.subscribe`, `channel.leave`,
`channel.list_subscriptions` and `s.ping`.

## Modules

| | |
|---|---|
| `consumer.py` | `VoteitConsumer` plus `SubscriptionMixin` and `ConnectionMixin`. One consumer for the whole app, mounted at `/ws/`. |
| `channels.py` | `PubSubChannel` / `ContextChannel` and the built-in `UserChannel`. Domain channels live in each app's `channels.py`. |
| `messages.py` | Protocol messages (`channel.*`, `s.*`), including the `channel.state` bundle. Deliberately **not** registered with `@outgoing` — they must not get `.batch` siblings. |
| `registry.py` | `@outgoing` / `@channel` targets, plus `app_state_collectors` and `collectors_for()`. `all_outgoing_messages()` feeds the consumer's `passthrough_events`. |
| `batch.py` | `make_batch()` — generates the `<action>.batch` sibling of an outgoing type. |
| `collectors.py` | `AppStateCollector`, the ABC each app subclasses in its own `collectors.py`. |
| `bundle.py` | Packs collector output into `channel.state` frames under `VOTEIT_APP_STATE_BUNDLE_BYTES`, and binds the bundle's payload union. |
| `utils.py` | `publish()`, `Target`, `TransactionBatcher`, and `_send_now()`, the single point where anything reaches the channel layer. |
| `presence.py` | `presence(window)` — who is online, in total and per organisation. Behind both the admin page and `manage.py online_connections`. |
| `close.py` | `close_session_connections()` / `close_user_connections()` / `close_all_connections()`. Server-initiated disconnects, which do **not** go through `utils.py` -- see below. |
| `jobs.py` | `build_subscription` plus `subscribe_job` / `recheck_job`, run on the `default` RQ queue, and `close_stale_connections` (see below). |
| `admin.py` | Read-only `Connection` admin, the `/admin/.../connection/online/` page and the stale-row action. |
| `state.py` | `AppState`, the accumulator collectors append to, grouped into `StateSection`s. |
| `values.py` | `wire_values()` / `wire_field_names()` — build a `.values()` payload whose keys come from a DRF serializer instead of a hand-written list. |
| `testing.py` | `MessageCatcher`, `ChannelMessageCatcher`, `build_app_state`, `build_bundles`, `run_collector`, `payloads_of`, `assert_frames_equal`, `unbundle`, `ws_test_settings`. |

## Adding an outgoing message

```python
@outgoing
class ThingChanged(ObjectAddedOrChanged):
    action: Literal["thing.changed"] = "thing.changed"
```

`@outgoing` also generates `ThingChangedBatch` (`thing.changed.batch`) and
registers both. There is no `*.added` — the client upserts on `*.changed`.

Publish with `SomeChannel(pk).sync_publish(msg)`. Inside a transaction the send
is deferred to commit, where `VOTEIT_BATCH_THRESHOLD` (3) or more of the same
action to the same target collapse into one batch. Groups leave in the order
their first message was added -- not full insertion order; see the
`TransactionBatcher` docstring before relying on one message preceding another.

`VOTEIT_WS_FAST_FANOUT` (default on) serialises a message once at the publisher
and lets each consumer forward the frame unchanged. Turning it off routes
through chanx's event dispatcher instead, which re-validates per recipient. The
frame the client sees is the same either way.

## Connect

An authenticated socket joins its own `user_<pk>` group and the
`session_<key>` group of the Django session that opened it, gets `s.versions`, and
is then subscribed to the organisation the user belongs to -- the client never
asks for it, because there is nothing to choose. That one stream is built
inline in `post_authentication` (`build_subscription` on Channels' sync thread)
rather than queued: `organisation.roles` is the only collector on the channel,
so the queue round trip would cost more than the work. A user without an
organisation (the FK is nullable only to ease testing) is subscribed to
nothing.

Everything the User model pushes -- `user.inv` -- goes to that channel too.
There is no longer an `online` group holding every open socket.

The two groups differ in blast radius, which is the whole reason both exist: a
logout closes `session_<key>`, so the tabs that actually lost their login go and
the same user's phone -- a different session, still valid -- stays. "Log out
everywhere" closes `user_<pk>` instead.

## Closing a socket from the server

`close.py` sends `s.close`; the consumer answers with `s.closing` and then closes.
That frame carries **nothing but a close code** — 1000 means stay out, 1001 that
the server is going away and the client should come back, and the two codes from
the application-private range say the session behind the socket is gone: 4000
(`LOGGED_OUT`) for an ordinary logout, 4001 (`LOGGED_OUT_EVERYWHERE`) when the
user logged out on every device. Anything the *user* should read beyond that is
a separate `s.msg`, which every function here sends first if given one, to the
same target so it cannot arrive after the socket has gone.

A logout sends no notice: the code already says what happened, and the client is
what knows how to word it — which is the whole reason the two logout cases have
separate codes. All four are in `NORMAL_CLOSE_CODES`, so neither a logout nor a
maintenance window reads as a wave of abnormal closures in the socket stats.

```python
close_session_connections(request.session.session_key, code=LOGGED_OUT)
close_user_connections(user.pk, code=LOGGED_OUT_EVERYWHERE, flush_session=True)
close_all_connections(notice=Notice(...))      # manage.py close_sockets
```

**Do not send `s.close` through `publish()` or `send_to_consumer()`.** It is not
registered with `@outgoing`, so with `VOTEIT_WS_FAST_FANOUT` on -- the default --
`_send_now` takes the passthrough route, which forwards the raw frame to the
browser and never runs an event handler. The client would receive
`{"action": "s.close"}`, ignore it, and stay connected. The close goes through
chanx's typed dispatcher instead, which is also why it is immediate rather than
deferred to commit by `TransactionBatcher` -- and why the notice beside it is
published with `on_commit=False`, or it would be flushed after the socket had
already gone.

`s.close` and `s.closing` deliberately have **separate payload classes**.
`flush_session` is an instruction to the consumer -- delete your own session on
the way out, which is how "log out everywhere" reaches a device whose session key
we cannot name -- and has no business on the wire. `close_connection` rebuilds the
outgoing payload rather than passing the incoming one through, because a
`CloseRequestPayload` satisfies the `ClosePayload` annotation and would serialise
its extra field along with the rest.

`close_all_connections` addresses sockets one at a time by `Connection.channel_name`,
since no group holds all of them; `manage.py close_sockets --message "..."` is the
operator front end. `manage.py online_connections` says how many that will be.

## Notices (`s.msg`)

`voteit.core.messages.notice.Notice` is a free-standing message to connected
clients: `{type, message}`, where `type` is `info` / `warning` / `error`. It is not part of the connection lifecycle and does not close anything,
so it is equally the thing to send beside a close and the thing to send on its
own.

## Connections and presence

`Connection` is one row per socket. There is **no FK to the user** -- rows
outlive the user they describe -- so every user-facing query goes through a
subquery (`user_id__in=User.objects.filter(...).values("pk")`).

`code` is the close code and is NULL while the socket is open, but Channels
never reports a consumer that died with its process, so an open row is only
evidence of presence when it has also been active recently. That is what
`Connection.objects.online(within)` means; `.stale(within)` is its complement
over the open rows, and both ride the `conn_open_last_action_idx` partial index.

`last_action` is written at most once per `VOTEIT_CONNECTION_UPDATE_INTERVAL`
seconds, and only when a message arrives -- `s.ping` is the de-facto heartbeat.
Every duration derived from it is an estimate.

`close_stale_connections` runs every 30 minutes and stamps `ABNORMAL_CLOSURE`
(1006) on rows silent for longer than `VOTEIT_CONNECTION_STALE_JOB_AFTER`. It
changes no visible number -- those rows were already outside every `online()`
window -- it just keeps the partial index small. A socket that turns out to be
alive heals itself: its next message sets `code` back to NULL. Setting
`VOTEIT_CONNECTION_RETENTION_DAYS` additionally purges long-closed rows.

## Counting who is online

`presence(window)` returns totals plus a per-organisation breakdown, both
counting users and sockets (one person with four tabs is one user and four
sockets). "Online" means open **and** active recently -- an open row on its own
is not evidence of presence, because Channels never reports a consumer that died
with its process.

It is the one implementation behind both the "Online now" admin page and
`manage.py online_connections [--window MINUTES]`, so the two cannot drift. The
grouping goes through `User`, since `Connection` has no organisation column;
`users_without_organisation` catches the case where the rows do not add up to the
total, which in production should be zero.

## Admin

- `/admin/voteit_messaging/connection/` -- read-only changelist, filterable by
  state (online / stale / closed) and organisation, sortable by duration.
- `/admin/voteit_messaging/connection/online/` -- live presence: users online,
  sockets per user, per-organisation breakdown, how long people have been
  connected, longest current sessions, stale count. `?window=` takes 5, 15 or 60.
- `/admin/dashboard/sockets/` -- `SocketStats` in `voteit/stats/dashboards.py`:
  connections opened per hour, session-length distribution, close codes.

## Gotchas

- Handlers run in a **background task**, so ordering between separately-sent
  messages is not guaranteed. Tests synchronise on the completion ack.
- `build_subscription` returns the whole stream instead of sending it, which
  is what lets the same code serve both `subscribe_job` and the inline
  organisation subscribe. It joins the group itself, so a caller that already
  holds an event loop has to reach it through `database_sync_to_async` -- a
  loose thread leaves a connection behind and deadlocks the test teardown.
- `jobs._send` and `jobs._send_state` take different routes on purpose.
  `channel.subscribed` / `channel.left` must go through chanx's typed
  dispatcher because `on_subscribed` / `on_left` maintain the consumer's own
  `channel_subs` set; bundles skip it, since re-validating a megabyte of nested
  models on the event loop is the cost this rework exists to remove — and
  `handle_channel_event` swallows a ValidationError with only a log line, which
  would make the whole initial state vanish silently.
- `bundle.bind_bundle_schema()` retargets `BundleSection.messages` at the real
  outgoing union *after* `autodiscover_modules("messages")`. It is the one
  thing here pydantic does not formally promise;
  `tests/test_bundle.py::BundleSchemaTests` is what tells you if it breaks. The
  fallback is the declared `SerializeAsAny[BaseMessage]`, which produces the
  same bytes and a vaguer schema.
- Don't name anything `self.subscriptions` on the consumer; chanx uses it for
  its own topic registry.
- `UserChannel.model` is bound in `AppConfig.ready()`, not as a classproperty:
  ABCMeta resolves abstract attributes at class-creation time, before the app
  registry can answer `get_user_model()`.
- The consumer reads the outgoing registry when its class is created, so every
  `messages.py` must be imported first (`autodiscover_modules`).
- `/asyncapi/docs/` (DEBUG) renders the full contract.
- The app label is `voteit_messaging`, not `messaging` (see `apps.py`), so admin
  URL names and template paths use that.
