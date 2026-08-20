"""Testing helpers for the websocket layer."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from django.conf import settings
from django.test import override_settings

from voteit.messaging.registry import action_of  # noqa: F401
from voteit.messaging.registry import context_channel_registry
from voteit.messaging.signals import channel_subscribed
from voteit.messaging.state import AppState

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage

    from voteit.messaging.channels import PubSubChannel
    from voteit.messaging.utils import Target

testing_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


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
    """Run the channel_subscribed receivers and return what they produced.

    Replaces constructing an envelope Subscribe message and calling
    get_app_state on it. ``user`` may be a user or a pk.
    """
    if isinstance(user, int):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.get(pk=user)
    channel_cls = context_channel_registry[channel_type]
    channel = channel_cls(pk)
    app_state = AppState()
    channel_subscribed.send(
        sender=channel_cls, context=channel.context, user=user, app_state=app_state
    )
    return app_state


def actions(messages) -> list[str]:
    return [m.action for m in messages]


def payloads_of(messages, message_cls: type[BaseMessage]) -> list:
    """Every payload of this type, whether or not it arrived batched.

    Lets a test assert on content without knowing if the receiver chose to
    batch, which is otherwise a constant source of breakage.
    """
    action = message_cls.model_fields["action"].default
    found = []
    for message in messages:
        if message.action == action:
            found.append(message.payload)
        elif message.action == f"{action}.batch":
            found.extend(message.payload.items)
    return found
