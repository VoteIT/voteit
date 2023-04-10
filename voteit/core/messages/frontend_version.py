from pydantic import BaseModel

from envelope.core.message import Message
from voteit.messaging.decorators import outgoing


class VersionSchema(BaseModel):
    version: str


@outgoing
class FrontendVersion(Message):
    name = "s.frontend_version"
    schema = VersionSchema
    data: VersionSchema
