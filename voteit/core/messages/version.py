from pydantic import BaseModel

from envelope.core.message import Message
from voteit.messaging.decorators import outgoing


class VersionSchema(BaseModel):
    backend: str
    frontend: str


@outgoing
class VersionMessage(Message):
    name = "s.versions"
    schema = VersionSchema
    data: VersionSchema
