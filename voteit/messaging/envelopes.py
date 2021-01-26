from pydantic import Field, BaseModel, validator
from typing import Dict, Optional
from voteit.messaging import INTERNAL_MESSAGE, WEBSOCKET_OUTGOING
from voteit.messaging.utils import get_outgoing_registry, get_incoming_registry


class BaseEnvelope(BaseModel):
    p: Dict = dict()
    t: str
    i: Optional[str] = None


class IncomingEnvelope(BaseEnvelope):
    """ Received from websocket - either a command or a query. """

    @validator("t")
    def validate_type(cls, v):
        registry = get_incoming_registry()
        if v not in registry:
            raise ValueError(f"No such incoming message type ({v})")
        return v


class InternalEnvelope(BaseEnvelope):
    """ A message sent to one or more consumers and meant to be acted upon there.
    """
    type: str = Field(INTERNAL_MESSAGE, const=True)
    # Which registry do we look for this message in, the incoming or outgoing?
    incoming: bool = False


class OutgoingEnvelope(BaseEnvelope):
    """ Transmission to an open websocket. Some kind of response or push. """
    type: str = Field(WEBSOCKET_OUTGOING, const=True)
    s: Optional[str]

    @validator("t")
    def validate_type(cls, v):
        registry = get_outgoing_registry()
        if v not in registry:
            raise ValueError(f"No such outgoing message type ({v})")
        return v
