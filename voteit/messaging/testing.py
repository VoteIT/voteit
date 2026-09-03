"""Testing helpers for the websocket layer."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.conf import settings
from django.test import override_settings

from voteit.messaging.bundle import iter_bundles
from voteit.messaging.messages import AppStateBundle
from voteit.messaging.registry import action_of  # noqa: F401
from voteit.messaging.registry import batch_for
from voteit.messaging.registry import app_state_collectors
from voteit.messaging.registry import collectors_for
from voteit.messaging.registry import context_channel_registry
from voteit.messaging.state import AppState

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage

    from voteit.messaging.channels import PubSubChannel
    from voteit.messaging.utils import Target

testing_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}

# Every websocket test has to send this.
#
# chanx builds its communicator from get_websocket_application(), which is the
# real ASGI stack -- AllowedHostsOriginValidator included. That validator denies
# a handshake whose Origin is missing entirely, unless ALLOWED_HOSTS contains
# "*". settings_development sets ["*"], so a test without an Origin connects
# locally; project.settings, which CI runs, does not, so the same test gets a
# close frame and connect() returns False. Django's setup_test_environment()
# already appends "testserver" to ALLOWED_HOSTS, so this origin is accepted
# under either settings module.
WS_TEST_ORIGIN_HEADER = (b"origin", b"http://testserver")


def ws_test_settings(cls_or_func):
    """Settings a consumer test needs.

    An in-memory channel layer, and SEND_COMPLETION on so that
    ``receive_all_messages()``'s default stop_action works. Production leaves
    completion off, and chanx re-reads its settings on Django's
    setting_changed signal, so overriding per test case is safe.
    """
    return override_settings(
        CHANNEL_LAYERS=testing_channel_layers_setting,
        CHANX={**settings.CHANX, "SEND_COMPLETION": True},
    )(cls_or_func)


def widen_receive_timeout(communicator, margin: float = 5) -> None:
    """Keep a drain's inner receive from expiring before the drain itself.

    ``receive_all_messages()`` wraps its own timeout around
    ``receive_json_from()`` using the *same* value, so both deadlines land in
    the same event-loop iteration. If the loop wakes up late -- a busy test
    suite is enough -- the inner one fires too, and asgiref reacts to that by
    cancelling the whole ASGI application task
    (``ApplicationCommunicator.receive_output``). The socket is dead from then
    on, and the next send raises ``CancelledError`` rather than anything that
    points at the cause.

    Pushing the inner deadline past the outer one means the drain's own
    timeout is always the one that fires.
    """
    # FIXME: This can be removed when ChanX updates.
    original = communicator.receive_json_from

    async def receive_json_from(timeout: float = 1):
        return await original(timeout + margin)

    communicator.receive_json_from = receive_json_from


class BaseMessageCatcher:
    """Collects messages, optionally filtered by type or action name."""

    def __init__(self, *args: type[BaseMessage] | str):
        actions = set()
        for arg in args:
            if isinstance(arg, str):
                actions.add(arg)
            elif isinstance(arg, type):
                actions.add(arg.model_fields["action"].default)
            else:
                raise TypeError("Filter args must be a string or a message type")
        self.filter = actions or None
        self.messages: list[BaseMessage] = []
        self.targets: list[Target] = []

    def _record(self, message: BaseMessage, target=None) -> None:
        if self.filter is None or message.action in self.filter:
            self.messages.append(message)
            self.targets.append(target)

    def __iter__(self):
        return iter(self.messages)

    def __len__(self) -> int:
        return len(self.messages)

    def __bool__(self) -> bool:
        return bool(self.messages)

    def __contains__(self, item) -> bool:
        if isinstance(item, str):
            return any(m.action == item for m in self.messages)
        return item in self.messages


class MessageCatcher(BaseMessageCatcher):
    """Catch everything on its way to the channel layer.

    Patches the single send chokepoint, so this sees group publishes, sends
    aimed at one consumer, and messages produced by the post-commit batcher --
    the envelope version only saw direct sends.

    >>> from voteit.core.messages.user import InvalidateUserCache
    >>> from voteit.messaging.utils import send_to_consumer
    >>> msg = InvalidateUserCache(payload={"pk": 1})
    >>> with MessageCatcher(InvalidateUserCache) as messages:
    ...     send_to_consumer(msg, "abc", on_commit=False)
    >>> len(messages)
    1
    >>> with MessageCatcher("only.this.action") as messages:
    ...     send_to_consumer(msg, "abc", on_commit=False)
    >>> len(messages)
    0
    """

    def __enter__(self) -> list[BaseMessage]:
        self._patch = patch(
            "voteit.messaging.utils._send_now", side_effect=self._record
        )
        self._patch.start()
        return self.messages

    def __exit__(self, *args):
        self._patch.stop()


class ChannelMessageCatcher(BaseMessageCatcher):
    """Catch what is published to one channel class.

    >>> from voteit.core.messages.user import InvalidateUserCache
    >>> from voteit.messaging.channels import UserChannel
    >>> msg = InvalidateUserCache(payload={"pk": 1})
    >>> with ChannelMessageCatcher(UserChannel) as messages:
    ...     UserChannel(1).sync_publish(msg, on_commit=False)
    >>> len(messages)
    1
    >>> with ChannelMessageCatcher(UserChannel, "only.this.action") as messages:
    ...     UserChannel(1).sync_publish(msg, on_commit=False)
    >>> len(messages)
    0
    """

    def __init__(self, channel: type[PubSubChannel], *args):
        super().__init__(*args)
        self.channel = channel

    def __enter__(self) -> list[BaseMessage]:
        self._patch = patch.object(self.channel, "sync_publish", return_value=None)
        self.mock = self._patch.start()
        return self.messages

    def __exit__(self, *args):
        self._patch.stop()
        for call in self.mock.mock_calls:
            if call.args:
                self._record(call.args[0])


def build_app_state(channel_type: str, pk: int, user) -> AppState:
    """Run a channel's collectors and return what they produced.

    The flat iterable most tests assert on, plus ``.sections`` for anything
    that cares which collector produced what. ``user`` may be a user or a pk.

    Unlike the subscribe job this does not swallow a collector's exception --
    a test wants the traceback, not a section quietly marked failed.
    """
    if isinstance(user, int):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.get(pk=user)
    channel_cls = context_channel_registry[channel_type]
    channel = channel_cls(pk)
    app_state = AppState()
    for collector_cls in collectors_for(channel_cls):
        collector = collector_cls(channel, user)
        if not collector.applicable():
            continue
        with app_state.section(collector.name):
            collector.collect(app_state)
    return app_state


def run_collector(name: str, context, user, *, channel_cls=None) -> AppState:
    """Run one named collector against an already-loaded context object.

    ``from_instance`` pre-seeds the channel's context, so an
    ``assertNumQueries`` around this measures the collector and nothing else.
    Both ``applicable()`` and ``collect()`` run: between them they are what the
    single ``channel_subscribed`` receiver used to do.

    Pass ``channel_cls`` for a collector registered on more than one channel --
    the participants/moderators pairs behave differently depending on which.
    """
    collector_cls = app_state_collectors[name]
    channel = (channel_cls or collector_cls.channels[0]).from_instance(context)
    collector = collector_cls(channel, user)
    app_state = AppState()
    if collector.applicable():
        with app_state.section(name):
            collector.collect(app_state)
    return app_state


def build_bundles(
    channel_type: str, pk: int, user, *, budget: int | None = None
) -> list[AppStateBundle]:
    """The channel.state frames a subscriber would actually receive."""
    app_state = build_app_state(channel_type, pk, user)
    return list(
        iter_bundles(
            app_state.sections, pk=pk, channel_type=channel_type, budget=budget
        )
    )


def unbundle(messages) -> Iterator[BaseMessage]:
    """Yield messages, replacing each channel.state frame with its contents.

    So a test can assert the same way whether it was handed an AppState, a
    MessageCatcher, or the bundles a consumer received.
    """
    for message in messages:
        if isinstance(message, AppStateBundle):
            for section in message.payload.sections:
                yield from section.messages
        else:
            yield message


def actions(messages) -> list[str]:
    return [m.action for m in unbundle(messages)]


def section_names(bundles) -> list[str]:
    """Collector names in the order their sections appear, without repeats."""
    names = []
    for bundle in bundles:
        for section in bundle.payload.sections:
            if section.name not in names:
                names.append(section.name)
    return names


def assert_frames_equal(
    test_case,
    message_cls: type[BaseMessage],
    from_values,
    from_serializer,
) -> None:
    """Assert two payload lists render the identical ``<action>.batch`` frame.

    The standard check for a collector that builds payloads with
    ``messaging.values.wire_values`` rather than its app's DRF serializer:
    running both through the real message class catches a key that is missing,
    renamed, or serialised differently -- a datetime rendered in another
    timezone, say -- which comparing the raw dicts would not.

    Pass querysets in a deterministic order; several of these models have no
    ``Meta.ordering`` and are free to come back in different orders.

    Empty input fails: two empty lists are trivially equal, and a fixture that
    quietly produces no rows would otherwise leave the test passing while
    asserting nothing.
    """
    values_items = list(from_values)
    serializer_items = list(from_serializer)
    test_case.assertTrue(
        values_items and serializer_items,
        "nothing to compare -- the test data produced no rows",
    )
    batch_cls = batch_for(message_cls)
    test_case.assertEqual(
        batch_cls(payload={"items": serializer_items}).model_dump(mode="json"),
        batch_cls(payload={"items": values_items}).model_dump(mode="json"),
    )


def payloads_of(messages, message_cls: type[BaseMessage]) -> list:
    """Every payload of this type, whether or not it arrived batched.

    Lets a test assert on content without knowing whether the collector chose
    to batch or how the bundler happened to split things up, which is
    otherwise a constant source of breakage.
    """
    action = message_cls.model_fields["action"].default
    found = []
    for message in unbundle(messages):
        if message.action == action:
            found.append(message.payload)
        elif message.action == f"{action}.batch":
            found.extend(message.payload.items)
    return found
