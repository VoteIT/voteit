"""
Shorthand decorators for registries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.utils import get_message_registry
from envelope.utils import get_context_channel_registry

if TYPE_CHECKING:
    from envelope.channels.models import ContextChannel
    from envelope.core.message import Message


def channel(channel: type[ContextChannel]):
    reg = get_context_channel_registry()
    reg[channel.name] = channel
    return channel


def outgoing(message: type[Message]):
    reg = get_message_registry(WS_OUTGOING)
    reg[message.name] = message
    return message


def incoming(message: type[Message]):
    reg = get_message_registry(WS_INCOMING)
    reg[message.name] = message
    return message
