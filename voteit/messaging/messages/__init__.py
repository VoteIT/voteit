from __future__ import annotations

import json
from logging import getLogger

from pydantic import BaseModel, validator
from typing import Optional, Dict

logger = getLogger(__name__)

# Basically specifies the function to receive the message with _ instead of . - see consumers
WEBSOCKET_OUTGOING_NAME = "websocket.send"
INTERNAL_MESSAGE = "internal.receive"


class IncomingPayload(BaseModel):
    """ Package received from websocket.
        p is the actual message in json.
    """
    p: Optional[str]  # Incoming payload isn't parsed here
    t: str  # Type, for instance "client.subscribe"
    i: Optional[str] = None  # A message id
    # Later on: ack


class OutgoingPayload(BaseModel):
    p: Optional[Dict]
    t: str  # Type, for instance "client.subscribe"
    i: Optional[str] = None  # A message id


class OutgoingErrorMessage(OutgoingPayload):
    e: Optional[Dict] = {}  # Errors?
    # FIXME: TBD


def register():
    """ Just make sure all code is imported and registered. """
    from . import channels, user, testing, agenda, schema
