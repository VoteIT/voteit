from pydantic import Field, BaseModel
from typing import Dict, Optional
from voteit.messaging import INTERNAL_MESSAGE, WEBSOCKET_OUTGOING


class BaseEnvelope(BaseModel):
    p: Dict
    t: str
    i: Optional[str]


class IncomingEnvelope(BaseEnvelope):
    """ Received from websocket - either a command or a query. """


class InternalEnvelope(BaseEnvelope):
    """ A message sent to one or more consumers and meant to be acted upon there.
    """
    type: str = Field(INTERNAL_MESSAGE, const=True)


class OutgoingEnvelope(BaseEnvelope):
    """ Transmission to an open websocket. Some kind of response or push. """
    type: str = Field(WEBSOCKET_OUTGOING, const=True)
    s: Optional[str]
