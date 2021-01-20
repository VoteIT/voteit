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
from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.text import TextResponse
from voteit.poll.models import Poll, Vote
from voteit.poll.permissions import VotePermissions


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
            raise Exception()  # Fixme
            # Vote already exists - no need to error we can simply change it instead?
            # msg = ChangeVote.from_message(self, vote=self.data.vote, pk=existing_vote.pk)
            # msg.send_internal(self.mm.consumer_name)
            # return msg
        else:
            Vote.objects.create(user=self.user, poll=self.context, vote=self.data.vote)
            msg = TextResponse.from_message(self, msg="Added")
            # FIXME: Vote might not be saved, add on_commit for send_outgoing
            msg.send_outgoing(self.mm.consumer_name, success=True)


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
