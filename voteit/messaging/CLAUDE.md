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
| `channels.py` | `PubSubChannel` / `ContextChannel` and the built-in `UserChannel` / `OnlineChannel`. Domain channels live in each app's `channels.py`. |
| `messages.py` | Protocol messages (`channel.*`, `s.*`). Deliberately **not** registered with `@outgoing` — they must not get `.batch` siblings. |
| `registry.py` | `@outgoing` / `@channel` targets. `all_outgoing_messages()` feeds the consumer's `passthrough_events`. |
| `batch.py` | `make_batch()` — generates the `<action>.batch` sibling of an outgoing type. |
| `utils.py` | `publish()`, `Target`, `TransactionBatcher`, and `_send_now()`, the single point where anything reaches the channel layer. |
| `jobs.py` | `subscribe_job` / `recheck_job`, run on the `default` RQ queue, plus `close_stale_connections` (see below). |
| `admin.py` | Read-only `Connection` admin, the `/admin/.../connection/online/` page and the stale-row action. |
| `state.py` | `AppState`, the accumulator receivers append to. |
| `testing.py` | `MessageCatcher`, `ChannelMessageCatcher`, `build_app_state`, `payloads_of`, `ws_test_settings`. |

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

## Subscribe

`channel.subscribe {channel_type, pk}` only enqueues; the worker checks
permission, joins the group and streams back:

```
channel.subscribed        <- channel metadata only
<action>.batch  x N       <- initial state, from channel_subscribed receivers
channel.state_complete
```

Contribute initial state by receiving `channel_subscribed` and calling
`app_state.add_batch(MessageCls, payloads)`.

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
