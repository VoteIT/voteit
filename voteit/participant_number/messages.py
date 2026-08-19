from abc import ABC
from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel


from voteit.messaging.decorators import outgoing
from voteit.messaging.base import ObjectDeleted


class PNSchema(BaseModel):
    meeting: int
    number: int
    user: int
    pk: int


class PNMessage(BaseMessage, ABC):
    payload: PNSchema


@outgoing
class PNChanged(PNMessage):
    action: Literal["pn.changed"] = "pn.changed"


@outgoing
class PNDeleted(ObjectDeleted):
    action: Literal["pn.deleted"] = "pn.deleted"
