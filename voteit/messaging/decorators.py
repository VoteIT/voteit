"""
Shorthand decorators for registries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from envelope import WS_OUTGOING
from envelope.utils import get_context_channel_registry
from envelope.utils import get_global_message_registry

if TYPE_CHECKING:
    from envelope.channels.models import ContextChannel
    from envelope.core.message import Message


def channel(channel: type[ContextChannel]):
    reg = get_context_channel_registry()
    reg[channel.name] = channel
    return channel


def outgoing(message: type[Message]):
    # setdefault rather than get_message_registry(): django.contrib.admin autodiscovery
    # imports app messages.py modules before envelope's AppConfig.ready() has run
    # register_envelopes(), so the namespace may not exist yet.
    reg = get_global_message_registry().setdefault(WS_OUTGOING, {})
    reg[message.name] = message
    return message
