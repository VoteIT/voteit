"""Generated ``<action>.batch`` sibling messages.

Envelope collapsed runs of same-type messages into one generic ``s.batch``
frame whose payloads were untyped. Here each outgoing message type instead
gets its own generated batch class, so batches validate like any other
message and show up in the AsyncAPI schema.
"""

from __future__ import annotations

from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel
from pydantic import create_model

BATCH_SUFFIX = ".batch"


def make_batch(message_cls: type[BaseMessage]) -> type[BaseMessage]:
    """Build the batch sibling of ``message_cls``.

    The result carries ``action = "<action>.batch"`` and a payload of
    ``{"items": [<the source payload schema>, ...]}``.

    ``create_model`` populates ``__annotations__`` before chanx's
    ``BaseMessage.__init_subclass__`` inspects it, so the generated class
    satisfies the "action must be a Literal" contract without any metaclass
    trickery.
    """
    action = message_cls.model_fields["action"].default
    payload_type = message_cls.model_fields["payload"].annotation
    if payload_type is None or payload_type is type(None):
        raise TypeError(
            f"{message_cls.__name__} has no payload type and cannot be batched"
        )
    batch_action = f"{action}{BATCH_SUFFIX}"

    payload_cls: type[BaseModel] = create_model(
        f"{message_cls.__name__}BatchPayload",
        items=(list[payload_type], ...),
        __module__=message_cls.__module__,
    )
    batch_cls: type[BaseMessage] = create_model(
        f"{message_cls.__name__}Batch",
        action=(Literal[batch_action], batch_action),
        payload=(payload_cls, ...),
        __base__=BaseMessage,
        __module__=message_cls.__module__,
        __doc__=f"Several {action} payloads delivered as one message.",
    )
    # Back-reference so the transaction batcher can get from a batch to the
    # type it collapsed.
    batch_cls.batched_type = message_cls
    return batch_cls
