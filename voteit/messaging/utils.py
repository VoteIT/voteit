"""Sending messages to the channel layer.

Everything funnels through :func:`_send_now`: group publishes, sends aimed at
one consumer, and post-commit batch flushes. That single chokepoint is what
the test helpers patch, and the only place that knows the channel-layer wire
format.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from channels import DEFAULT_CHANNEL_LAYER
from channels.layers import get_channel_layer
from django.conf import settings
from django.db.transaction import get_connection

from voteit.messaging.registry import maybe_batch_for

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage


@dataclass(frozen=True)
class Target:
    """Where a message is going.

    ``group`` distinguishes a channel-layer group (fan-out to every subscriber)
    from a single consumer's own channel name.
    """

    name: str
    group: bool = True
    layer: str = DEFAULT_CHANNEL_LAYER


def _send_now(message: BaseMessage, target: Target) -> None:
    """Hand one message to the channel layer. The single chokepoint."""
    layer = get_channel_layer(target.layer)
    assert layer is not None, "No channel layer configured"
    payload = {
        "type": "handle_group_message",
        "message": message.model_dump(mode="json"),
        "exclude_current": False,
        "from_channel": "",
    }
    if target.group:
        async_to_sync(layer.group_send)(target.name, payload)
    else:
        async_to_sync(layer.send)(target.name, payload)


def publish(message: BaseMessage, target: Target, *, on_commit: bool = True) -> None:
    """Send a message, batching with others in the same transaction.

    With ``on_commit`` inside an atomic block the send is deferred to commit,
    where runs of the same action to the same target collapse into one
    ``<action>.batch`` message.
    """
    if on_commit:
        batcher = _get_or_create_batcher()
        if batcher is not None:
            batcher.add(message, target)
            return
    _send_now(message, target)


def send_to_consumer(
    message: BaseMessage, channel_name: str, *, on_commit: bool = True
) -> None:
    """Send to one consumer rather than fanning out to a group."""
    publish(message, Target(channel_name, group=False), on_commit=on_commit)


class TransactionBatcher:
    """Collects sends during an atomic block and collapses them on commit.

    Replaces envelope's TransactionSender. Grouping is by (action, target);
    insertion order is preserved across groups so that, say, the proposals a
    poll refers to still arrive before the poll does.
    """

    def __init__(self) -> None:
        self.data: list[tuple[BaseMessage, Target]] = []

    def add(self, message: BaseMessage, target: Target) -> None:
        self.data.append((message, target))

    def __call__(self) -> None:
        for message, target in self.collapse():
            _send_now(message, target)

    def collapse(self) -> list[tuple[BaseMessage, Target]]:
        threshold = getattr(settings, "VOTEIT_BATCH_THRESHOLD", 3)
        grouped: dict[tuple[str, Target], list[BaseMessage]] = defaultdict(list)
        order: list[tuple[str, Target]] = []
        for message, target in self.data:
            key = (message.action, target)
            if key not in grouped:
                order.append(key)
            grouped[key].append(message)

        result: list[tuple[BaseMessage, Target]] = []
        for key in order:
            messages = grouped[key]
            target = key[1]
            # None for a message that is already a batch, or for one that was
            # never registered with @outgoing. Both go out as they are: this
            # runs from an on_commit hook, after the write has been committed,
            # so raising here would lose every message still queued behind it.
            batch_cls = maybe_batch_for(type(messages[0]))
            if len(messages) >= threshold and batch_cls is not None:
                result.append(
                    (
                        batch_cls(payload={"items": [m.payload for m in messages]}),
                        target,
                    )
                )
            else:
                result.extend((m, target) for m in messages)
        return result


def _get_or_create_batcher(using=None) -> TransactionBatcher | None:
    """The batcher for the current atomic block, or None if there isn't one."""
    conn = get_connection(using=using)
    if not conn.in_atomic_block:
        return None
    for entry in conn.run_on_commit:
        # entry is (sids, func) or (sids, func, robust) depending on version
        func = entry[1]
        if isinstance(func, TransactionBatcher):
            return func
    batcher = TransactionBatcher()
    conn.on_commit(batcher)
    return batcher
