from __future__ import annotations

from logging import getLogger
from typing import List
from typing import Optional
from pydantic import Field
from pydantic import root_validator
from pydantic import validator
from pydantic.main import BaseModel
from typing import Set

from voteit.invites.exceptions import InviteError
from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.utils import create_invites
from voteit.invites.utils import get_dispatchers_registry
from voteit.invites.utils import get_invite_data_registry
from voteit.invites.utils import create_dispatch_and_schedule_invites
from voteit.invites.workflows import InviteWf
from voteit.core.validators import root_validate_roles_and_model
from voteit.core.workflows import SendWf
from voteit.meeting.models import Meeting
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import ContextAction
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.errors import BadRequestError
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted


logger = getLogger(__name__)


class AddInvitesSchema(BaseModel):
    roles: List[str]
    model: str = Field("meeting", const=True)  # Constant
    skip_states: Set[str] = Field(
        {InviteWf.REJECTED}, const=True
    )  # Allow changes later
    invite_data: List[str]
    type: str = "email"
    meeting: int

    # Validators
    _check_roles = root_validator(skip_on_failure=True, allow_reuse=True)(
        root_validate_roles_and_model
    )

    @validator("type")
    def validate_type(cls, v):
        if v not in get_invite_data_registry():
            raise ValueError(f"{v} is not a valid type")
        return v

    @root_validator(skip_on_failure=True)
    def validate_invite_data(cls, values):
        """
        >>> AddInvitesSchema(roles=['participant'], invite_data=['hello@betahaus.net'], meeting=1)
        AddInvitesSchema(roles=['participant'], model='meeting', skip_states={'rejected'}, invite_data=['hello@betahaus.net'], type='email', meeting=1)

        >>> AddInvitesSchema(roles=['participant'], invite_data=['HELLO@betahaus.net'], meeting=1)
        AddInvitesSchema(roles=['participant'], model='meeting', skip_states={'rejected'}, invite_data=['hello@betahaus.net'], type='email', meeting=1)

        >>> AddInvitesSchema(roles=['participant'], invite_data=['bad_email'], meeting=1)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:

        >>> AddInvitesSchema(roles=['participant'], invite_data=['something'], meeting=1)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:

        >>> AddInvitesSchema(roles=['participant'], invite_data=None, meeting=1)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:
        """
        reg = get_invite_data_registry()
        # Delegate all validation to the registry
        values["invite_data"] = reg.validate(values["type"], values["invite_data"])
        return values


@incoming
class AddInvites(BaseIncomingMessage, ContextAction, DeferredJob):
    name = "invites.add"
    permission = MeetingInvitePermissions.ADD
    schema = AddInvitesSchema
    data: AddInvitesSchema
    model = Meeting
    context_pk_attr = "meeting"

    def run_job(self) -> InvitesAdded:
        """
        Bulk create invites. If an invite already exist for that data,
        update the invite and make sure the user has those roles. Think of the new invite as a desired state.
        If a role is added or removed, that should be reflected back on that user.

        """
        self.assert_perm()
        try:
            added, changed, skipped_count = create_invites(
                created_by=self.user, **self.data.dict()
            )
        except InviteError as exc:
            raise BadRequestError.from_message(
                self,
                msg=exc.message,
            )
        response = InvitesAdded.from_message(
            self,
            added=added,
            changed=changed,
            skipped_count=skipped_count,
        )
        response.send_outgoing(self.mm.consumer_name, success=True)
        return response


class InvitesAddedSchema(BaseModel):
    added: List[int]
    changed: List[int]
    skipped_count: int = 0


@outgoing
class InvitesAdded(BaseOutgoingMessage):
    name = "invites.added"
    schema = InvitesAddedSchema
    data: InvitesAddedSchema


VALID_STATES = set(SendWf.states.keys()) - {SendWf.SENDING, SendWf.SCHEDULED}


class SendInvitesSchema(BaseModel):
    meeting: int
    subject: Optional[str]  # FIXME - None means default from send dispatcher
    body: str  # FIXME
    states: List[str] = [SendWf.FAILED, SendWf.SENT, SendWf.CREATED]
    dispatcher_name: str = "send_email"
    resend_minimum: int = 24  # Don't resend before this

    @validator("states")
    def validate_states(cls, v: List[str]):
        """
        >>> SendInvitesSchema.validate_states(['hello'])
        Traceback (most recent call last):
        ...
        ValueError:

        >>> SendInvitesSchema.validate_states([SendWf.SENT, SendWf.CREATED])
        ['sent', 'created']

        """
        specified = set(v)
        invalid = specified - VALID_STATES
        if invalid:
            raise ValueError(
                f"The following invite send states aren't valid: '{', '.join(invalid)}'"
            )
        return v

    @validator("dispatcher_name")
    def validate_dispatcher_name(cls, v: str):
        """
        >>> SendInvitesSchema.validate_dispatcher_name('hello')
        Traceback (most recent call last):
        ...
        ValueError:

        >>> SendInvitesSchema.validate_dispatcher_name('send_email')
        'send_email'

        """
        reg = get_dispatchers_registry()
        if v not in reg:
            raise ValueError(f"No invite dispatcher with the name '{v}'")
        return v


@incoming
class SendInvites(BaseIncomingMessage, ContextAction, DeferredJob):
    name = "invites.send"
    permission = MeetingInvitePermissions.ADD
    schema = SendInvitesSchema
    data: SendInvitesSchema
    model = Meeting
    context_pk_attr = "meeting"
    job_atomic = False

    def run_job(self):
        self.assert_perm()
        invite_dispatch = create_dispatch_and_schedule_invites(
            created_by=self.user, **self.data.dict()
        )
        invite_dispatch.send_scheduled()


@outgoing
class MeetingInviteAdded(BaseObjectAdded):
    name = "meeting_invite.added"


@outgoing
class MeetingInviteChanged(BaseObjectChanged):
    name = "meeting_invite.changed"


@outgoing
class MeetingInviteDeleted(BaseObjectDeleted):
    name = "meeting_invite.deleted"
