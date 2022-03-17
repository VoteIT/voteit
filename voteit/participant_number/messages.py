from pydantic import BaseModel

from envelope.core.message import Message

from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseObjectDeleted


class PNSchema(BaseModel):
    meeting: int
    number: int
    user: int
    pk: int


class PNMessage(Message):
    schema = PNSchema
    data: PNSchema


@outgoing
class PNAdded(PNMessage):
    name = "pn.added"


@outgoing
class PNChanged(PNMessage):
    name = "pn.changed"


@outgoing
class PNDeleted(BaseObjectDeleted):
    name = "pn.deleted"
