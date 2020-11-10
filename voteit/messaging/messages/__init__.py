from __future__ import annotations

from logging import getLogger

from pydantic import BaseModel, validator
from typing import Optional, Union

logger = getLogger(__name__)

# Basically specifies the function to receive the message with _ instead of . - see consumers
WEBSOCKET_OUTGOING_NAME = "websocket.send"
INTERNAL_MESSAGE = "internal.receive"


class IncomingPayload(BaseModel):
    """ Package received from websocket.
        p is the actual message in json.
    """
    t: str  # Type, for instance "client.subscribe"
    p: dict  # The actual message
    i: Optional[str] = None  # A message id
    # Later on: ack

    # @validator("p")
    # def reasonable_payload(cls, v):
    #     if not v:  # Empty payloads are probably okay for some messages
    #         return v
    #     if v.startswith("{") and v.endswith("}"):
    #         return v
    #     raise ValueError("Payload should start with '{' and end with '}'")


class OutgoingPayload(BaseModel):
    t: str  # Type, for instance "client.subscribe"
    p: dict  # The actual message in json
    i: Optional[str] = None  # A message id


class OutgoingErrorMessage(OutgoingPayload):
    e: Union[dict, str] = {}  # Errors?
    # FIXME: TBD


def register():
    """ Just make sure all code is imported and registered. """
    from . import channels, user, testing, agenda, schema
