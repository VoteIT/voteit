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
| `jobs.py` | `subscribe_job` / `recheck_job`, run on the `default` RQ queue. |
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
action to the same target collapse into one batch.

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
