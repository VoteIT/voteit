"""
Shorthand decorators for registries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.messaging.registry import register_channel
from voteit.messaging.registry import register_outgoing

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage

    from voteit.messaging.channels import ContextChannel


def channel(channel: type[ContextChannel]) -> type[ContextChannel]:
    return register_channel(channel)


def outgoing(message: type[BaseMessage]) -> type[BaseMessage]:
    """Register a message the server pushes to clients.

    Also generates its ``<action>.batch`` sibling -- see
    voteit.messaging.batch.
    """
    return register_outgoing(message)
