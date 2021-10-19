from __future__ import annotations

from datetime import timedelta
from logging import getLogger
from typing import Dict
from typing import List
from typing import Optional
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext as _
from pydantic import Field
from pydantic import root_validator
from pydantic import validator
from pydantic.main import BaseModel

from voteit.access_policy.models import MeetingInvite
from voteit.access_policy.permissions import MeetingInvitePermissions
from voteit.access_policy.utils import get_dispatchers_registry
from voteit.access_policy.utils import get_invite_data_registry
from voteit.access_policy.utils import create_dispatch_and_schedule_invites
from voteit.access_policy.workflows import InviteWf
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

if TYPE_CHECKING:
    from voteit.access_policy.models import InviteDispatch

logger = getLogger(__name__)


class AddInvitesSchema(BaseModel):
    roles: List[str]
    model: str = Field("meeting", const=True)  # Constant
    invite_data: List[Dict[str, str]]
    meeting: int

    # Validators
    _check_roles = root_validator(skip_on_failure=True, allow_reuse=True)(
        root_validate_roles_and_model
    )

    @validator("invite_data")
    def validate_invite_data(cls, v):
        """
        >>> AddInvitesSchema(roles=['participant'], invite_data=[{'email': 'hello@betahaus.net'}], meeting=1)
        AddInvitesSchema(roles=['participant'], model='meeting', invite_data=[{'email': 'hello@betahaus.net'}], meeting=1)

        >>> AddInvitesSchema(roles=['participant'], invite_data=[{'email': 'bad_email'}], meeting=1)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:

        >>> AddInvitesSchema(roles=['participant'], invite_data=[{'bad_scope': 'something'}], meeting=1)
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
        for row in v:
            reg.validate(row)
        return v


@incoming
class AddInvites(BaseIncomingMessage, ContextAction, DeferredJob):
    name = "invites.add"
    permission = MeetingInvitePermissions.ADD
    schema = AddInvitesSchema
    data: AddInvitesSchema
    model = Meeting
    context_pk_attr = "meeting"
    _SKIP_STATES = {InviteWf.REVOKED, InviteWf.REVOKED}

    def run_job(self) -> InvitesAdded:
        """
        Bulk create invites. If an invite already exist for that data,
        update the invite and make sure the user has those roles. Think of the new invite as a desired state.
        If a role is added or removed, that should be reflected back on that user.

        """
        self.assert_perm()
        meeting: Meeting = self.context
        added = []
        changed = []
        skipped_count = 0
        i = 1
        for row in self.data.invite_data:
            invite_qs = meeting.invites.filter_on_any(row)
            if invite_qs.exists():
                # First filter out excludable
                invite_qs = invite_qs.exclude(state__in=self._SKIP_STATES)
                if not invite_qs.exists():
                    skipped_count += 1
                    continue
                # Do we hit multiple active invites?
                if invite_qs.count() > 1:
                    raise BadRequestError.from_message(
                        self,
                        msg=_(
                            "Data on row %(row)s matched different invites that already exist. You need to clear them first."
                        )
                        % {"row": i},
                    )
                # So we need to update this single existing invite and set permissions according to the new state
                invite: MeetingInvite = invite_qs.first()
                user = invite.used_by
                if user:
                    # Adjust existing roles
                    requested_roles = set(invite.roles)
                    current_roles = meeting.get_roles(user)
                    if not current_roles:
                        current_roles = set()
                    remove_roles = requested_roles - current_roles
                    if remove_roles:
                        meeting.remove_roles(user, *remove_roles)
                    add_roles = current_roles - requested_roles
                    if add_roles:
                        meeting.add_roles(user, *add_roles)
                # Update invite
                invite.invite_data = row
                invite.roles = self.data.roles
                invite.last_modified_by = self.user
                invite.save()
                changed.append(invite.pk)
            else:
                # We need to create a new invite
                invite = meeting.invites.create(
                    invite_data=row,
                    created_by=self.user,
                    roles=self.data.roles,
                    last_modified_by=self.user,
                )
                added.append(invite.pk)
            i += 1
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
