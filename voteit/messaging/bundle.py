"""Packing a channel's initial state into as few frames as possible.

Subscribing used to cost one channel-layer round trip and one websocket frame
per message, and a busy ``MeetingChannel`` produces dozens. Here the collectors'
output is packed into ``channel.state`` bundles instead: sections from
consecutive collectors are appended until the byte budget is reached, so an
ordinary meeting arrives in a single frame.

The budget (``VOTEIT_APP_STATE_BUNDLE_BYTES``, 1 MB) is well under daphne's
``--websocket-max-message-size`` of 5 MiB, which is the only hard ceiling in the
stack -- redis and channels_redis limit queue *depth*, not message size.
"""

from __future__ import annotations

import json
from logging import getLogger
from typing import TYPE_CHECKING
from typing import Annotated
from typing import Iterable
from typing import Iterator
from typing import Union

from chanx.messages.base import BaseMessage
from django.conf import settings
from pydantic import BaseModel
from pydantic import Field

from voteit.messaging.messages import AppStateBundle
from voteit.messaging.messages import AppStateBundlePayload
from voteit.messaging.messages import BundleSection

if TYPE_CHECKING:
    from voteit.messaging.state import StateSection

logger = getLogger(__name__)

# The ``{"action": ..., "payload": {"pk": ..., "sections": []}}`` wrapper.
FRAME_OVERHEAD = 256
# ``{"name": ..., "complete": true, "failed": false, "messages": []},``
SECTION_OVERHEAD = 64


def budget_bytes() -> int:
    return getattr(settings, "VOTEIT_APP_STATE_BUNDLE_BYTES")


def _json_size(obj) -> int:
    """Serialised size in bytes, measured once and then reused.

    Pydantic's own serialiser rather than ``json.dumps``: it is what produces
    the bytes that actually go on the wire, so the count matches.
    """
    if isinstance(obj, BaseModel):
        return len(obj.__pydantic_serializer__.to_json(obj))
    return len(json.dumps(obj, default=str).encode())


def _section_overhead(name: str) -> int:
    return SECTION_OVERHEAD + len(name.encode())


def _split_batch(message: BaseMessage, limit: int) -> Iterator[tuple[BaseMessage, int]]:
    """Re-chunk one oversized ``<action>.batch`` into several that fit.

    Generated batch classes keep a ``batched_type`` back-reference and hold
    their payloads in ``payload.items`` (see :mod:`voteit.messaging.batch`), so
    a smaller batch of the same type is just a new instance over a slice.

    Anything else -- a single message that is simply too big -- is yielded as
    it is. There is no smaller frame to put it in, and it is still far under
    daphne's limit.
    """
    batch_cls = type(message)
    items = getattr(message.payload, "items", None)
    if getattr(batch_cls, "batched_type", None) is None or not items:
        size = _json_size(message)
        logger.warning(
            "Initial state message %s is %s bytes, over the %s bytes a section "
            "has to spend, and is not a batch that could be split",
            message.action,
            size,
            limit,
        )
        yield message, size
        return

    envelope = _json_size(batch_cls(payload={"items": []}))
    chunk: list = []
    chunk_size = 0
    for item in items:
        # + 1 for the comma separating this item from the previous one.
        item_size = _json_size(item) + 1
        if chunk and envelope + chunk_size + item_size > limit:
            yield batch_cls(payload={"items": chunk}), envelope + chunk_size
            chunk, chunk_size = [], 0
        chunk.append(item)
        chunk_size += item_size
    if chunk:
        yield batch_cls(payload={"items": chunk}), envelope + chunk_size


def _sized(
    messages: Iterable[BaseMessage], limit: int
) -> list[tuple[BaseMessage, int]]:
    """Measure every message, splitting any that could never fit on its own."""
    sized: list[tuple[BaseMessage, int]] = []
    for message in messages:
        size = _json_size(message)
        if size <= limit:
            sized.append((message, size))
        else:
            sized.extend(_split_batch(message, limit))
    return sized


def iter_bundles(
    sections: Iterable[StateSection],
    *,
    pk: int,
    channel_type: str,
    budget: int | None = None,
) -> Iterator[AppStateBundle]:
    """Pack collector sections into ``channel.state`` messages.

    Every section appears at least once, even when its collector produced
    nothing -- it was announced on ``channel.subscribed``, so the client is
    waiting for it to be marked complete. A section whose messages do not all
    fit is emitted repeatedly with ``complete=False`` until the last piece.

    >>> from voteit.core.messages.user import InvalidateUserCache
    >>> from voteit.messaging.state import StateSection
    >>> section = StateSection("demo.things")
    >>> section.messages = [InvalidateUserCache(payload={"pk": i}) for i in range(3)]
    >>> bundles = list(iter_bundles([section], pk=1, channel_type="meeting"))
    >>> len(bundles)
    1
    >>> bundles[0].action
    'channel.state'
    >>> bundles[0].payload.seq, bundles[0].payload.pk
    (0, 1)
    >>> [(s.name, s.complete, len(s.messages)) for s in bundles[0].payload.sections]
    [('demo.things', True, 3)]

    A budget too small to hold everything spills into further bundles, and only
    the final piece of a section is marked complete:

    >>> bundles = list(
    ...     iter_bundles([section], pk=1, channel_type="meeting", budget=FRAME_OVERHEAD + 120)
    ... )
    >>> [(b.payload.seq, s.name, s.complete, len(s.messages))
    ...  for b in bundles for s in b.payload.sections]
    [(0, 'demo.things', False, 1), (1, 'demo.things', False, 1), (2, 'demo.things', True, 1)]
    """
    usable = max((budget or budget_bytes()) - FRAME_OVERHEAD, SECTION_OVERHEAD + 1)
    seq = 0
    packed: list[BundleSection] = []
    used = 0

    def bundle(number: int, entries: list[BundleSection]) -> AppStateBundle:
        return AppStateBundle(
            payload={
                "pk": pk,
                "channel_type": channel_type,
                "seq": number,
                "sections": entries,
            }
        )

    for section in sections:
        overhead = _section_overhead(section.name)
        pieces = _sized(section.messages, usable - overhead)
        index = 0
        while True:
            head: list[BaseMessage] = []
            head_size = 0
            while index < len(pieces):
                message, size = pieces[index]
                # An empty bundle always takes at least one message, however
                # big: flushing again would not make room and the loop would
                # never advance.
                if (packed or head) and used + overhead + head_size + size > usable:
                    break
                head.append(message)
                head_size += size
                index += 1
            done = index >= len(pieces)
            if head or done:
                packed.append(
                    BundleSection(
                        name=section.name,
                        complete=done,
                        failed=section.failed,
                        messages=head,
                    )
                )
                used += overhead + head_size
            if done:
                break
            yield bundle(seq, packed)
            seq += 1
            packed, used = [], 0

    if packed:
        yield bundle(seq, packed)


def bind_bundle_schema() -> None:
    """Point ``BundleSection.messages`` at the real outgoing union.

    Cannot happen at class-definition time: the union is every ``@outgoing``
    type plus its ``.batch`` sibling, and almost none of them exist when
    ``messages.py`` is imported. So the field is declared permissively and
    retargeted here, once ``autodiscover_modules("messages")`` has run -- the
    same shape as ``MessagingConfig.ready()`` binding ``UserChannel.model``.

    Idempotent, and a no-op while the registry is still empty, so it is safe to
    call from both the app config and the consumer module.
    """
    from voteit.messaging.registry import all_outgoing_messages

    outgoing = all_outgoing_messages()
    if len(outgoing) < 2:  # pragma: no coverage
        # Nothing discovered yet, or too few types to form a union at all.
        return
    union = Annotated[Union[tuple(outgoing)], Field(discriminator="action")]
    BundleSection.model_fields["messages"].annotation = list[union]
    # Child first: each parent regenerates its core schema from the one below.
    BundleSection.model_rebuild(force=True)
    AppStateBundlePayload.model_rebuild(force=True)
    AppStateBundle.model_rebuild(force=True)
