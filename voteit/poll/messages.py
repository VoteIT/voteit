from pydantic.main import BaseModel
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.messages.base import BaseObjectAdded, BaseObjectChanged, BaseObjectDeleted
from voteit.messaging.registries import outgoing_messages


@outgoing_messages
class PollAdded(BaseObjectAdded):
    name = "poll.added"


@outgoing_messages
class PollChanged(BaseObjectChanged):
    name = "poll.changed"


@outgoing_messages
class PollDeleted(BaseObjectDeleted):
    name = "poll.deleted"


class PollStatusSchema(BaseModel):
    pk: int
    voted: int
    total: int


@outgoing_messages
class PollStatus(BaseOutgoingMessage):
    name = "poll.status"
    schema = PollStatusSchema
    data: PollStatusSchema
