from __future__ import annotations

from logging import getLogger

from django.utils.translation import gettext as _
from pydantic import Field
from pydantic import root_validator
from pydantic import validator
from pydantic.main import BaseModel

from auditlog.context import set_actor
from envelope.core.message import ContextAction
from envelope.core.message import Message
from envelope.messages.errors import BadRequestError
from envelope.utils import websocket_send
from voteit.core.validators import root_validate_roles_and_model
from voteit.core.workflows import SendWf
from voteit.invites.exceptions import InviteError
from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.utils import create_dispatch_and_schedule_invites
from voteit.invites.utils import create_invites
from voteit.invites.utils import get_dispatchers_registry
from voteit.invites.utils import get_invite_data_registry
from voteit.invites.workflows import InviteWf
from voteit.meeting.models import Meeting
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing

logger = getLogger(__name__)


class AddInvitesSchema(BaseModel):
    roles: list[str]
    model: str = Field("meeting", const=True)  # Constant
    skip_states: set[str] = {InviteWf.REJECTED}
    invite_data: list[str]
    type: str
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
        >>> AddInvitesSchema(roles=['participant'], type="email", invite_data=['hello@betahaus.net'], meeting=1)
        AddInvitesSchema(roles=['participant'], model='meeting', skip_states={'rejected'}, invite_data=['hello@betahaus.net'], type='email', meeting=1)

        >>> AddInvitesSchema(roles=['participant'], type="email", invite_data=['HELLO@betahaus.net'], meeting=1)
        AddInvitesSchema(roles=['participant'], model='meeting', skip_states={'rejected'}, invite_data=['hello@betahaus.net'], type='email', meeting=1)

        Blankspace should be skipped or trimmed
        >>> AddInvitesSchema(roles=['participant'], type="email", invite_data=['', '    WoHo@betahaus.net', ' '], meeting=1)
        AddInvitesSchema(roles=['participant'], model='meeting', skip_states={'rejected'}, invite_data=['woho@betahaus.net'], type='email', meeting=1)

        >>> AddInvitesSchema(roles=['participant'], type="email", invite_data=['bad_email'], meeting=1)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:

        No real data
        >>> AddInvitesSchema(roles=['participant'], type="email", invite_data=['  ', ''], meeting=1)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:

        >>> AddInvitesSchema(roles=['participant'], type="email", invite_data=['something'], meeting=1)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:

        >>> AddInvitesSchema(roles=['participant'], type="email", invite_data=None, meeting=1)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError:
        """
        reg = get_invite_data_registry()
        # Delegate all validation to the registry
        invite_type = values["type"]
        if invite_type not in reg:
            raise ValueError("No such invite type")
        inv_count = len(values["invite_data"])
        if inv_count > 1000:
            raise ValueError(
                _(
                    "More than 1 000 invites at once isn't allowed. You sent %(inv_count)s rows."
                    % {"inv_count": inv_count}
                )
            )
        validator = reg[invite_type]
        results = []
        i = 1
        for v in values["invite_data"]:
            v = v.strip()
            if v:
                try:
                    inst = validator(
                        **{invite_type: v}
                    )  # Might raise pydantics ValidationError
                except ValueError:
                    raise ValueError(
                        f"Row {i} contains invite data that doesn't match type '{invite_type}'"
                    )
                results.append(getattr(inst, invite_type))
            i += 1
        if not results:
            raise ValueError("invite_data required")
        values["invite_data"] = results
        return values


@incoming
class AddInvites(ContextAction):
    name = "invites.add"
    permission = MeetingInvitePermissions.ADD
    schema = AddInvitesSchema
    data: AddInvitesSchema
    model = Meeting
    context_schema_attr = "meeting"
    job_timeout = 30

    def run_job(self) -> InvitesAdded:
        """
        Bulk create invites. If an invite already exist for that data,
        update the invite and make sure the user has those roles. Think of the new invite as a desired state.
        If a role is added or removed, that should be reflected back on that user.

        """
        self.assert_perm()

        try:
            with set_actor(self.user):
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
        websocket_send(response, state=response.SUCCESS)
        return response


class InvitesAddedSchema(BaseModel):
    added: list[int]
    changed: list[int]
    skipped_count: int = 0


@outgoing
class InvitesAdded(Message):
    name = "invites.added"
    schema = InvitesAddedSchema
    data: InvitesAddedSchema


VALID_STATES = set(SendWf.states.keys()) - {SendWf.SENDING, SendWf.SCHEDULED}


class SendInvitesSchema(BaseModel):
    meeting: int
    subject: str | None  # FIXME - None means default from send dispatcher
    body: str  # FIXME
    states: list[str] = [SendWf.FAILED, SendWf.SENT, SendWf.CREATED]
    dispatcher_name: str = "send_email"
    resend_minimum: int = 24  # Don't resend before this

    @validator("states")
    def validate_states(cls, v: list[str]):
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
class SendInvites(ContextAction):
    name = "invites.send"
    permission = MeetingInvitePermissions.ADD
    schema = SendInvitesSchema
    data: SendInvitesSchema
    model = Meeting
    context_schema_attr = "meeting"
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
