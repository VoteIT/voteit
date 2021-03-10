from typing import Dict
from typing import Optional
from typing import Union

from pydantic import BaseModel
from pydantic import Field
from pydantic import validator
from voteit.messaging import INTERNAL_MESSAGE
from voteit.messaging import WEBSOCKET_OUTGOING
from voteit.messaging.utils import get_incoming_registry
from voteit.messaging.utils import get_outgoing_registry


class BaseEnvelope(BaseModel):
    p: Union[Dict, str] = dict()
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
    """A message sent to one or more consumers and meant to be acted upon there."""

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
