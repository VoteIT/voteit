from __future__ import annotations

from abc import ABC

from pydantic.main import BaseModel

from voteit.messaging.abcs import (
    BaseOutgoingMessage,
    BaseIncomingMessage,
    DeferredJob,
    ContextAction,
)
from voteit.messaging.messages.base import (
    BaseObjectAdded,
    BaseObjectChanged,
    BaseObjectDeleted,
)
from voteit.messaging.decorators import outgoing, incoming
from voteit.messaging.messages.text import TextResponse
from voteit.poll.models import Poll, Vote
from voteit.poll.permissions import VotePermissions
from voteit.poll.schemas import GenericVoteSchema


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

    def validate_vote(self) -> None:
        """ Run extra validation based on the specific poll method implementation.
        """


class AddVote(VoteBase, ABC):
    """ The base class for adding votes.
    """

    permission = VotePermissions.ADD
    model = Poll

    def run_job(self):
        self.assert_perm()
        self.validate_vote()
        existing_vote = self.context.votes.filter(user=self.user).first()
        if existing_vote is not None:
            # Vote already exists - no need to error we can simply change it instead?
            # A bit hackish, lets guess the change name
            base_name = self.name.split('.')[0]
            type_name = f"{base_name}.change"
            msg = ChangeVote.from_message(self, type_name=type_name, vote=self.data.vote, pk=existing_vote.pk)
            msg.send_internal(self.mm.consumer_name)
            TextResponse.from_message(self, msg="Changed").send_outgoing(self.mm.consumer_name, success=True)
            return msg
        else:
            Vote.objects.create(user=self.user, poll=self.context, vote=self.data.vote)
            msg = TextResponse.from_message(self, msg="Added")
            # FIXME: Vote might not be saved, add on_commit for send_outgoing
            msg.send_outgoing(self.mm.consumer_name, success=True)
            return msg


class AbstainSchema(BaseModel):
    pk: int  # Poll pk for votes


@incoming
class AbstainVote(VoteBase):
    """ Abstain from voting in this poll
    """
    permission = VotePermissions.ADD
    model = Poll
    name = "vote.abstain"
    schema = AbstainSchema
    data: AbstainSchema

    def run_job(self):
        self.assert_perm()
        poll: Poll = self.context
        existing_vote: Vote = poll.votes.filter(user=self.user).first()
        if existing_vote is None:
            poll.votes.create(user=self.user, abstain=True)
        else:
            existing_vote.abstain = True
            existing_vote.save()
        msg = TextResponse.from_message(self, msg="Abstained")
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


class ChangeVote(VoteBase, ABC):
    """ Update a users vote. Subclass this and register as an incoming
        message for each poll method, with a proper vote schema.
    """

    permission = VotePermissions.CHANGE
    model = Vote

    def run_job(self):
        self.assert_perm()
        self.validate_vote()
        self.context.vote = self.data.vote
        self.context.save()


@incoming
class GetVote(VoteBase):  # TODO Make sure this reports abstain votes
    """ Get users vote in a generic format.
    """
    name = "vote.get"
    permission = VotePermissions.VIEW
    model = Vote

    def run_job(self) -> GenericVoteResponse:
        self.assert_perm()
        msg = GenericVoteResponse.from_message(self, vote=self.context.vote, pk=self.context.pk)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@outgoing
class GenericVoteResponse(BaseOutgoingMessage):
    name = "vote.get"
    schema = GenericVoteSchema
    data: GenericVoteSchema
