from __future__ import annotations

from collections import UserList
from collections.abc import Iterable
from typing import TYPE_CHECKING

from voteit.messaging.registry import batch_for

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage


class AppState(UserList):
    """Accumulator for the messages that make up a channel's initial state.

    Receivers of ``channel_subscribed`` append to one of these; the subscribe
    job then streams the contents to the client.
    """

    def append(self, item: BaseMessage) -> None:
        from chanx.messages.base import BaseMessage as _BaseMessage

        if not isinstance(item, _BaseMessage):
            raise TypeError(f"Expected a BaseMessage, got {type(item).__name__}")
        super().append(item)

    def add_batch(self, message_cls: type[BaseMessage], payloads: Iterable) -> None:
        """Append one ``<action>.batch`` message, or nothing if empty.

        Initial state is almost always many payloads of the same type, so this
        is the usual way for a receiver to contribute.
        """
        items = list(payloads)
        if items:
            super().append(batch_for(message_cls)(payload={"items": items}))
