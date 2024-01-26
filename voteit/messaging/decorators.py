"""
Shorthand decorators for registries.
"""

from typing import Type

from envelope.core.channels import ContextChannel
from envelope.core.message import Message
from envelope.registries import context_channel_registry
from envelope.registries import ws_outgoing_messages
from envelope.registries import ws_incoming_messages


def channel(channel: Type[ContextChannel]):
    context_channel_registry.add(channel)
    return channel


def outgoing(message: Type[Message]):
    ws_outgoing_messages.add(message)
    return message


def incoming(message: Type[Message]):
    ws_incoming_messages.add(message)
    return message
