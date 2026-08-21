"""Registries for outgoing messages and context channels.

VoteIT owns these rather than chanx: the consumer needs a single list of every
outgoing type to declare as ``passthrough_events``, and ``channel.subscribe``
dispatches on a channel-type name rather than a handler per domain.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from django.core.exceptions import ImproperlyConfigured

from voteit.messaging.batch import make_batch

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage

    from voteit.messaging.channels import ContextChannel

# action -> message class, including generated .batch siblings
_outgoing: dict[str, type[BaseMessage]] = {}
# source message class -> its generated batch class
_batch_for: dict[type[BaseMessage], type[BaseMessage]] = {}
# channel type name -> channel class
context_channel_registry: dict[str, type[ContextChannel]] = {}


def action_of(message_cls: type[BaseMessage]) -> str:
    return message_cls.model_fields["action"].default


def register_outgoing(message_cls: type[BaseMessage]) -> type[BaseMessage]:
    """Register an outgoing message type and generate its batch sibling."""
    action = action_of(message_cls)
    existing = _outgoing.get(action)
    if existing is not None and existing is not message_cls:
        raise ImproperlyConfigured(
            f"Duplicate outgoing action {action!r}: "
            f"{existing.__module__}.{existing.__name__} and "
            f"{message_cls.__module__}.{message_cls.__name__}"
        )
    _outgoing[action] = message_cls

    batch_cls = make_batch(message_cls)
    _outgoing[action_of(batch_cls)] = batch_cls
    _batch_for[message_cls] = batch_cls
    # Bind the generated class onto its source module so that get_type_hints,
    # pickling and the AsyncAPI schema all resolve it by name.
    setattr(sys.modules[message_cls.__module__], batch_cls.__name__, batch_cls)
    return message_cls


def register_channel(channel_cls: type[ContextChannel]) -> type[ContextChannel]:
    existing = context_channel_registry.get(channel_cls.name)
    if existing is not None and existing is not channel_cls:
        raise ImproperlyConfigured(
            f"Duplicate channel name {channel_cls.name!r}: "
            f"{existing.__name__} and {channel_cls.__name__}"
        )
    context_channel_registry[channel_cls.name] = channel_cls
    return channel_cls


def batch_for(message_cls: type[BaseMessage]) -> type[BaseMessage]:
    """The batch sibling of an outgoing message type."""
    batch_cls = maybe_batch_for(message_cls)
    if batch_cls is None:
        raise LookupError(
            f"{message_cls.__name__} is not registered as an outgoing message; "
            "decorate it with @outgoing"
        )
    return batch_cls


def maybe_batch_for(message_cls: type[BaseMessage]) -> type[BaseMessage] | None:
    """The batch sibling, or None if this type cannot be batched.

    A generated ``<action>.batch`` class has no sibling of its own, so anything
    that collapses a run of messages has to cope with being handed one -- see
    ``TransactionBatcher.collapse``, which runs inside an on_commit hook where
    raising would be far worse than not batching.
    """
    return _batch_for.get(message_cls)


def all_outgoing_messages() -> list[type[BaseMessage]]:
    """Every outgoing type plus its batch sibling, for passthrough_events."""
    return list(_outgoing.values())


def get_outgoing(action: str) -> type[BaseMessage]:
    return _outgoing[action]
