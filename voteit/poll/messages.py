from __future__ import annotations

from abc import ABC

from django.contrib.auth.models import AbstractUser
from pydantic import validator
from pydantic.main import BaseModel
from typing import List

from envelope import WS_INCOMING
from envelope.core.message import ContextAction
from envelope.core.message import Message
from envelope.utils import get_message_type
from envelope.utils import websocket_send
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.permissions import ElectoralRegisterPermissions
from voteit.poll.permissions import VotePermissions
from voteit.poll.rest_api.serializers import VoteSerializer
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


class PollStatusSchema(BaseModel):
    pk: int
    voted: int
    total: int


@outgoing
class PollStatus(Message):
    name = "poll.status"
    schema = PollStatusSchema
    data: PollStatusSchema


class VoteBase(ContextAction, ABC):
    ...


class AddVote(VoteBase, ABC):
    """The base class for adding votes."""

    permission = VotePermissions.ADD
    model = Poll
    context: Poll
    context_schema_attr = "poll"

    def run_job(self):
        self.assert_perm()
        poll = self.context
        poll.method.validate_vote(self)
        existing_vote = poll.votes.filter(user=self.user).first()
        if existing_vote is not None:
            # Vote already exists - no need to error we can simply change it instead?
            # A bit hackish, lets guess the change name
            base_name = self.name.split(".")[0]
            type_name = f"{base_name}.change"
            change_vote_type = get_message_type(type_name, WS_INCOMING)
            assert issubclass(change_vote_type, ChangeVote)
            msg = change_vote_type.from_message(
                self, vote=self.data.vote, pk=existing_vote.pk
            )
            websocket_send(msg, state=msg.SUCCESS)
            return msg
        else:
            vote = poll.votes.create(user=self.user, vote=self.data.vote)
            serializer = VoteSerializer(vote)
            msg = GenericVoteResponse.from_message(self, **serializer.data)
            websocket_send(msg, state=msg.SUCCESS)
            return msg


class AbstainSchema(BaseModel):
    poll: int  # Poll pk for votes


@incoming
class AbstainVote(VoteBase):
    """Abstain from voting in this poll"""

    permission = VotePermissions.ADD
    model = Poll
    name = "vote.abstain"
    schema = AbstainSchema
    data: AbstainSchema
    context: Poll
    context_schema_attr = "poll"

    def run_job(self):
        self.assert_perm()
        poll = self.context
        vote: Vote = poll.votes.filter(user=self.user).first()
        if vote is None:
            vote = poll.votes.create(user=self.user, abstain=True)
        else:
            vote.abstain = True
            vote.save()
        serializer = VoteSerializer(vote)
        msg = GenericVoteResponse.from_message(self, **serializer.data)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


class ChangeVote(VoteBase, ABC):
    """Update a users vote. Subclass this and register as an incoming
    message for each poll method, with a proper vote schema.
    """

    context: Vote
    permission = VotePermissions.CHANGE
    model = Vote

    def run_job(self):
        self.assert_perm()
        poll: Poll = self.context.poll
        poll.method.validate_vote(self)
        self.context.vote = self.data.vote
        self.context.abstain = False
        self.context.save()
        serializer = VoteSerializer(self.context)
        msg = GenericVoteResponse.from_message(self, **serializer.data)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@outgoing
class GenericVoteResponse(Message):
    name = "vote.added"
    schema = AddedVoteSchema
    data: AddedVoteSchema


class GetERVoteCountSchema(BaseModel):
    electoral_register: int


@incoming
class GetERVoteCount(ContextAction):
    """Returns vote count for each user in a specific electoral register."""

    name = "er.vote_count"
    permission = ElectoralRegisterPermissions.VIEW
    model = ElectoralRegister
    context: ElectoralRegister
    schema = GetERVoteCountSchema
    data: GetERVoteCountSchema
    context_schema_attr = "electoral_register"

    def run_job(self) -> ERVoteCount:
        self.assert_perm()
        er = self.context
        weights = [
            {"user": x.user, "weight": x.weight} for x in er.voterweight_set.all()
        ]
        msg = ERVoteCount.from_message(
            self,
            total=er.get_total_vote_weight(),
            weights=weights,
        )
        websocket_send(msg, state=msg.SUCCESS)
        return msg


class VoteWeight(BaseModel):
    user: int
    weight: int

    @validator("user", pre=True)
    def transform_user(cls, value):
        if isinstance(value, int):
            return value
        elif isinstance(value, AbstractUser):
            return value.pk
        raise ValueError("Wrong user type")


class ERVoteCountSchema(BaseModel):
    weights: List[VoteWeight]
    total: int


@outgoing
class ERVoteCount(Message):
    name = "er.vote_count"
    schema = ERVoteCountSchema
    data: ERVoteCountSchema
