from typing import Literal
from chanx.messages.base import BaseMessage
from pydantic import BaseModel

from voteit.messaging.decorators import outgoing


class VersionSchema(BaseModel):
    backend: str
    frontend: str


@outgoing
class VersionMessage(BaseMessage):
    action: Literal["s.versions"] = "s.versions"
    payload: VersionSchema
