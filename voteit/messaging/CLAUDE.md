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
| `jobs.py` | `build_subscription` plus `subscribe_job` / `recheck_job`, run on the `default` RQ queue, and `close_stale_connections` (see below). |
| `admin.py` | Read-only `Connection` admin, the `/admin/.../connection/online/` page and the stale-row action. |
| `state.py` | `AppState`, the accumulator collectors append to, grouped into `StateSection`s. |
| `testing.py` | `MessageCatcher`, `ChannelMessageCatcher`, `build_app_state`, `build_bundles`, `run_collector`, `payloads_of`, `unbundle`, `ws_test_settings`. |

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

An authenticated socket joins its own `user_<pk>` group, gets `s.versions`, and
is then subscribed to the organisation the user belongs to -- the client never
asks for it, because there is nothing to choose. That one stream is built
inline in `post_authentication` (`build_subscription` on Channels' sync thread)
rather than queued: `organisation.roles` is the only collector on the channel,
so the queue round trip would cost more than the work. A user without an
organisation (the FK is nullable only to ease testing) is subscribed to
nothing.

Everything the User model pushes -- `user.inv` -- goes to that channel too.
There is no longer an `online` group holding every open socket.

## Subscribe

`channel.subscribe {channel_type, pk}` only enqueues; the worker checks
permission, joins the group and streams back:

```
channel.subscribed    <- channel metadata + the names of every contributing collector
channel.state  x N    <- the initial state itself, usually one frame
channel.state_complete
```

A `channel.state` payload is `{pk, channel_type, seq, sections}`, where each
section is one collector's output:

```json
{"name": "poll.own_votes", "complete": true, "failed": false,
 "messages": [{"action": "vote.changed.batch", "payload": {"items": [...]}}]}
```

`complete` is False when that collector's output continues in the next bundle;
`failed` means it raised, so what is there is partial. Sections are packed
until `VOTEIT_APP_STATE_BUNDLE_BYTES` (1 MB), so an ordinary meeting arrives in
a single frame instead of the dozens of loose messages this replaced.

### Contributing initial state

Declare a collector in the owning app's `collectors.py` (autodiscovered):

```python
@app_state_collectors
class Polls(AppStateCollector):
    name = "poll.polls"              # goes on the wire; must be unique
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 50                       # 10 structural, 50 content, 200 user-specific

    def applicable(self) -> bool:    # cheap; False = skipped and never announced
        return True

    def collect(self, state: AppState) -> None:
        state.add_batch(PollChanged, serializer.data)
```

`self.channel`, `self.context` and `self.user` are set for you. A collector
registered on several channels branches on `self.channel` — that is how the
participants/moderators visibility pairs work.

There is no `meeting` channel. Anything meeting-wide now
goes through `voteit.meeting.channels.broadcast_meeting`, which publishes to both
groups, and every collector that used to serve `meeting` declares
`channels = (ParticipantsChannel, ModeratorsChannel)`.

A collector that raises only loses its own section (`failed: true`); the rest
still run. The exception is a database error, which leaves the durable atomic
block unusable and is re-raised — there is deliberately no savepoint per
collector.

**Prefer `.values()` to a ModelSerializer for anything bulk.** Six models carry
a `python-statemachine` machine (`Meeting`, `AgendaItem`, `Proposal`, `Poll`,
`SpeakerListSystem`, `MeetingInvite`). This used to be the dominant cost:
`MachineMixin.__init__` built a whole machine — callback registries and
dispatchers — for *every* instance, measured at **120 kB per model instance
against 0.4 kB per `.values()` row, 280x**. `StateMachineModelMixin` made that
binding lazy (`voteit/core/statemachines.py`), so a model instance now costs
about 0.6 kB and the machine is built only when something reads `.sm`. Skipping
the instance is still cheaper, but this is now a DRF-overhead argument, not an
order-of-magnitude one — do not contort a collector to avoid model instances.

`agenda.items` and `proposal.collectors.attach_proposals` both take the
`.values()` route for this reason. It is only valid while the serializer has no
method fields or nested serializers, so assert the equivalence rather than
assume it — see `voteit/agenda/tests/test_collectors.py`. `poll.polls` and
`invites.invites` still serialize instances; neither converts safely
(`SerializerMethodField`, `PydanticFieldSerializer`, M2M), so they remain the
two places where a very large meeting will show up in worker memory.

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
