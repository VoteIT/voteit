from pydantic.main import BaseModel
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.decorators import outgoing


class TextSchema(BaseModel):
    msg: str


@outgoing
class TextResponse(BaseOutgoingMessage):
    name = "response.text"
    schema = TextSchema
    data: TextSchema
