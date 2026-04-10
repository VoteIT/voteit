from __future__ import annotations

from abc import ABC

from auditlog.context import set_actor
from pydantic.main import BaseModel

from envelope.deferred_jobs.message import ContextAction
from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.messages.errors import ValidationErrorMsg
from envelope.messages.errors import BadRequestError
from envelope.utils import websocket_send

from voteit.core import PERM
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.poll.app.er_policies.manual import Manual
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.schemas import AddedVoteSchema
from voteit.poll.schemas import VotersWeightsSchema


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


class ManualCreateERSchema(VotersWeightsSchema):
    # Contains weights too
    meeting: int


@incoming
class ManualCreateER(ContextAction):
    """
    Manually create an electoral register based on voter weight.
    This can be used regardless of the meetings electoral register setting, but with a stern warning
    that another policy may overwrite this at any moment.

    Only users with potential_voter role will be considered.
    """

    name = "er.manual_create"
    schema = ManualCreateERSchema
    data: ManualCreateERSchema
    model = Meeting
    context_schema_attr = "meeting"
    permission = ElectoralRegister.get_perm(PERM.ADD)

    def run_job(self) -> Status:
        self.assert_perm()
        # Check that each of the users is a potential voter
        potential_voters = set(
            self.context.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        )
        missing_potential_voters = {
            x.user for x in self.data.weights if x.user not in potential_voters
        }
        if missing_potential_voters:
            # FIXME: Error dict with pos as int
            raise ValidationErrorMsg.from_message(
                self,
                msg=f"Got the following invalid potential voters (User PKs): {', '.join([str(x) for x in sorted(missing_potential_voters)])}",
                errors=[],
            )
        weight_dict = {wv.user: wv.weight for wv in self.data.weights}
        manual_er = Manual(self.context)
        with set_actor(self.user):
            manual_er.create_er(weight_dict=weight_dict)  # Only creates if needed
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


class TriggerERResponseSchema(BaseModel):
    created: bool


@outgoing
class TriggerERResponse(Message):
    name = "er.trigger_response"
    schema = TriggerERResponseSchema
    data: TriggerERResponseSchema


class TriggerCreateERSchema(BaseModel):
    meeting: int


@incoming
class TriggerCreateER(ContextAction):
    """
    Manually trigger creation of an ER for automatic methods.
    """

    name = "er.trigger_create"
    schema = TriggerCreateERSchema
    data: TriggerCreateERSchema
    model = Meeting
    context_schema_attr = "meeting"
    permission = ElectoralRegister.get_perm(PERM.ADD)

    def run_job(self) -> TriggerERResponse:
        meeting: Meeting = self.context
        if not meeting.valid_er_policy_guard():
            raise BadRequestError.from_message(self, msg="No valid electoral registry")
        if not meeting.er_policy.allow_trigger:
            raise BadRequestError.from_message(
                self, msg="Electoral register can't be triggered this way"
            )
        self.assert_perm()
        latest_er = meeting.latest_er
        with set_actor(self.user):
            new_er = meeting.er_policy.create_er()
            created = new_er and latest_er != new_er
        msg = TriggerERResponse.from_message(self, created=bool(created))
        websocket_send(msg, state=msg.SUCCESS)
        return msg
