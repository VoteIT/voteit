from __future__ import annotations

from abc import ABC
from typing import Union

from django.contrib.auth.models import AbstractUser
from pydantic import validator
from pydantic.main import BaseModel
from typing import List

from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import ContextAction
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted
from voteit.messaging.messages.text import TextResponse
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
class PollStatus(BaseOutgoingMessage):
    name = "poll.status"
    schema = PollStatusSchema
    data: PollStatusSchema


class VoteBase(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    context_pk_attr = "pk"


class AddVote(VoteBase, ABC):
    """The base class for adding votes."""

    permission = VotePermissions.ADD
    model = Poll
    context: Poll
    context_pk_attr = "poll"

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
            msg = ChangeVote.from_message(
                self, type_name=type_name, vote=self.data.vote, pk=existing_vote.pk
            )
            msg.send_internal(self.mm.consumer_name)
            return msg
        else:
            vote = poll.votes.create(user=self.user, vote=self.data.vote)
            serializer = VoteSerializer(vote)
            msg = GenericVoteResponse.from_message(self, **serializer.data)
            msg.send_outgoing(self.mm.consumer_name, success=True)
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
    context_pk_attr = "poll"

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
        msg.send_outgoing(self.mm.consumer_name, success=True)
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
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


class GetVoteSchema(BaseModel):
    poll: int  # Poll!


@incoming
class GetVote(VoteBase):
    """Get users vote in a generic format."""

    name = "vote.get"
    permission = VotePermissions.ADD
    model = Poll
    context: Poll
    schema = GetVoteSchema
    data: GetVoteSchema
    context_pk_attr = "poll"

    def run_job(self) -> Union[GenericVoteResponse, TextResponse]:
        self.assert_perm()
        poll = self.context
        try:
            vote: Vote = poll.votes.get(user=self.user)
            msg = GenericVoteResponse.from_message(
                self, vote=vote.vote, abstain=vote.abstain, pk=vote.pk
            )
            msg.send_outgoing(self.mm.consumer_name, success=True)
            return msg
        except Vote.DoesNotExist:
            msg = TextResponse.from_message(self, msg="No vote")
            msg.send_outgoing(self.mm.consumer_name, success=False)
            return msg


@outgoing
class GenericVoteResponse(BaseOutgoingMessage):
    name = "vote.added"
    schema = AddedVoteSchema
    data: AddedVoteSchema


class GetERVoteCountSchema(BaseModel):
    electoral_register: int


@incoming
class GetERVoteCount(BaseIncomingMessage, DeferredJob, ContextAction):
    """ Returns vote count for each user in a specific electoral register."""

    name = "er.vote_count"
    permission = ElectoralRegisterPermissions.VIEW
    model = ElectoralRegister
    context: ElectoralRegister
    schema = GetERVoteCountSchema
    data: GetERVoteCountSchema
    context_pk_attr = "electoral_register"

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
        msg.send_outgoing(self.mm.consumer_name, success=True)
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
class ERVoteCount(BaseOutgoingMessage):
    name = "er.vote_count"
    schema = ERVoteCountSchema
    data: ERVoteCountSchema
