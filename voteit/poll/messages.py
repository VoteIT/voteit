from __future__ import annotations

from abc import ABC

from auditlog.context import set_actor
from pydantic.main import BaseModel

from envelope.deferred_jobs.message import ContextAction
from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.utils import websocket_send

from voteit.core import PERM
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.poll.models import Poll
from voteit.poll.models import Vote
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


class VoteBase(ContextAction, ABC): ...


class AddVote(VoteBase, ABC):
    """
    The base class for adding votes.
    There's no change vote, so this updates an existing vote if it exists.
    """

    permission = Vote.get_perm(PERM.ADD)
    model = Poll
    context: Poll
    context_schema_attr = "poll"
    atomic = True

    def run_job(self):
        self.assert_perm()
        poll = self.context
        poll.method.validate_vote(self)
        with set_actor(self.user):
            poll.votes.update_or_create(
                user=self.user, defaults={"vote": self.data.vote, "abstain": False}
            )
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)


class AbstainSchema(BaseModel):
    poll: int  # Poll pk for votes


@incoming
class AbstainVote(VoteBase):
    """Abstain from voting in this poll"""

    permission = Vote.get_perm(PERM.ADD)
    model = Poll
    name = "vote.abstain"
    schema = AbstainSchema
    data: AbstainSchema
    context: Poll
    context_schema_attr = "poll"
    atomic = True

    def run_job(self):
        self.assert_perm()
        poll = self.context
        with set_actor(self.user):
            poll.votes.update_or_create(
                user=self.user, defaults={"abstain": True, "vote": None}
            )
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)


@outgoing
class GenericVoteResponse(Message):
    name = "vote.added"
    schema = AddedVoteSchema
    data: AddedVoteSchema


