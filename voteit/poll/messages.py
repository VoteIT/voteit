from __future__ import annotations

from typing import Literal
from chanx.messages.base import BaseMessage

from pydantic.main import BaseModel


from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing
from voteit.poll.schemas import AddedVoteSchema


@outgoing
class PollChanged(ObjectAddedOrChanged):
    action: Literal["poll.changed"] = "poll.changed"


@outgoing
class PollDeleted(ObjectDeleted):
    action: Literal["poll.deleted"] = "poll.deleted"


@outgoing
class ElectoralRegisterAdded(ObjectAddedOrChanged):
    action: Literal["er.changed"] = "er.changed"


@outgoing
class ElectoralRegisterDeleted(ObjectDeleted):
    action: Literal["er.deleted"] = "er.deleted"


@outgoing
class VoteTransferChanged(ObjectAddedOrChanged):
    action: Literal["vt.changed"] = "vt.changed"


@outgoing
class VoteTransferDeleted(ObjectDeleted):
    action: Literal["vt.deleted"] = "vt.deleted"


class PollStatusSchema(BaseModel):
    pk: int
    voted: int
    total: int


@outgoing
class PollStatus(BaseMessage):
    action: Literal["poll.status"] = "poll.status"
    payload: PollStatusSchema


@outgoing
class GenericVoteResponse(BaseMessage):
    action: Literal["vote.changed"] = "vote.changed"
    payload: AddedVoteSchema
