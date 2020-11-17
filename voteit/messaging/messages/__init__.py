from __future__ import annotations

from logging import getLogger

from pydantic import BaseModel
from typing import Optional, Dict


logger = getLogger(__name__)

# Basically specifies the function to receive the message with _ instead of . - see consumers
WEBSOCKET_OUTGOING_NAME = "websocket.send"
INTERNAL_MESSAGE = "internal.receive"


class IncomingPayload(BaseModel):
    """ Package received from websocket.
        p is the actual message.
    """
    p: Optional[Dict]  # Incoming payload
    t: str  # Type, for instance "client.subscribe"
    i: Optional[str] = None  # A message id


class MsgState:
    SUCCESS = "s"
    FAILED = "f"
    WAITING = "w"
    RUNNING = "r"


class OutgoingPayload(BaseModel):
    p: Optional[Dict]
    t: str  # Type, for instance "client.subscribe"
    i: Optional[str] = None  # A message id
    s: str = ""  # State


class OutgoingErrorMessage(OutgoingPayload):
    e: Optional[Dict] = {}  # FIXME: I have no clue yet - TBD ;)


def register():
    """ Just make sure all code is imported and registered. """
    from . import channels, user, agenda, schema, progress, discussion_post, proposal, poll
    from django.conf import settings

    if settings.DEBUG:
        from . import testing
