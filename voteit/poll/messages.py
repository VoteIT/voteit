from __future__ import annotations

from pydantic.main import BaseModel

from envelope.core.message import Message

from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import outgoing
from voteit.poll.schemas import AddedVoteSchema


@outgoing
class PollAdded(BaseObjectAdded):
    name = "poll.added"


@outgoing
class PollChanged(BaseObjectChanged):
    name = "poll.changed"


@outgoing
class PollDeleted(BaseObjectDeleted):
    name = "poll.deleted"


@outgoing
class ElectoralRegisterAdded(BaseObjectAdded):
    name = "er.added"


@outgoing
class ElectoralRegisterDeleted(BaseObjectDeleted):
    name = "er.deleted"


@outgoing
class VoteTransferAdded(BaseObjectAdded):
    name = "vt.added"


@outgoing
class VoteTransferChanged(BaseObjectChanged):
    name = "vt.changed"


@outgoing
class VoteTransferDeleted(BaseObjectDeleted):
    name = "vt.deleted"


class PollStatusSchema(BaseModel):
    pk: int
    voted: int
    total: int


@outgoing
class PollStatus(Message):
    name = "poll.status"
    schema = PollStatusSchema
    data: PollStatusSchema


@outgoing
class GenericVoteResponse(Message):
    name = "vote.added"
    schema = AddedVoteSchema
    data: AddedVoteSchema
