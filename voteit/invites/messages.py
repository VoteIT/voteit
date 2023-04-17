from __future__ import annotations

from logging import getLogger

from auditlog.context import set_actor
from pydantic.main import BaseModel

from envelope.core.message import ContextAction
from envelope.core.message import Message
from envelope.messages.errors import BadRequestError
from envelope.utils import websocket_send
from voteit.invites.exceptions import InviteError
from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.schemas import AddTypedInvitesSchema
from voteit.meeting.models import Meeting
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing

logger = getLogger(__name__)


@incoming
class AddInvites(ContextAction):
    name = "invites.add"
    permission = MeetingInvitePermissions.ADD
    schema = AddTypedInvitesSchema
    data: AddTypedInvitesSchema
    model = Meeting
    context_schema_attr = "meeting"
    job_timeout = 40

    def run_job(self) -> InvitesAdded:
        """
        Bulk create invites. If an invite already exist for that data,
        update the invite and make sure the user has those roles. Think of the new invite as a desired state.
        If a role is added or removed, that should be reflected back on that user.

        """
        self.assert_perm()
        try:
            with set_actor(self.user):
                (
                    added,
                    changed,
                    skipped,
                ) = self.context.invites.create_or_update_typed(
                    meeting=self.context,
                    roles=self.data.roles,
                    values=self.data.user_data,
                    exclude_states=self.data.skip_states,
                    invite_type=self.data.type,
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
            skipped=skipped,
        )
        if response.mm.consumer_name:  # In case it was run by a script
            websocket_send(response, state=response.SUCCESS)
        return response


class InvitesAddedSchema(BaseModel):
    added: int = 0
    changed: int = 0
    skipped: int = 0


@outgoing
class InvitesAdded(Message):
    name = "invites.added"
    schema = InvitesAddedSchema
    data: InvitesAddedSchema


# VALID_STATES = set(SendWf.states.keys()) - {SendWf.SENDING, SendWf.SCHEDULED}
#
#
# class SendInvitesSchema(BaseModel):
#     meeting: int
#     subject: str | None  # FIXME - None means default from send dispatcher
#     body: str  # FIXME
#     states: list[str] = [SendWf.FAILED, SendWf.SENT, SendWf.CREATED]
#     dispatcher_name: str = "send_email"
#     resend_minimum: int = 24  # Don't resend before this
#
#     @validator("states")
#     def validate_states(cls, v: list[str]):
#         """
#         >>> SendInvitesSchema.validate_states(['hello'])
#         Traceback (most recent call last):
#         ...
#         ValueError:
#
#         >>> SendInvitesSchema.validate_states([SendWf.SENT, SendWf.CREATED])
#         ['sent', 'created']
#
#         """
#         specified = set(v)
#         invalid = specified - VALID_STATES
#         if invalid:
#             raise ValueError(
#                 f"The following invite send states aren't valid: '{', '.join(invalid)}'"
#             )
#         return v
#
#     @validator("dispatcher_name")
#     def validate_dispatcher_name(cls, v: str):
#         """
#         >>> SendInvitesSchema.validate_dispatcher_name('hello')
#         Traceback (most recent call last):
#         ...
#         ValueError:
#
#         >>> SendInvitesSchema.validate_dispatcher_name('send_email')
#         'send_email'
#
#         """
#         reg = get_dispatchers_registry()
#         if v not in reg:
#             raise ValueError(f"No invite dispatcher with the name '{v}'")
#         return v
#
#
# @incoming
# class SendInvites(ContextAction):
#     name = "invites.send"
#     permission = MeetingInvitePermissions.ADD
#     schema = SendInvitesSchema
#     data: SendInvitesSchema
#     model = Meeting
#     context_schema_attr = "meeting"
#     job_atomic = False
#
#     def run_job(self):
#         self.assert_perm()
#         invite_dispatch = create_dispatch_and_schedule_invites(
#             created_by=self.user, **self.data.dict()
#         )
#         invite_dispatch.send_scheduled()


@outgoing
class MeetingInviteAdded(BaseObjectAdded):
    name = "meeting_invite.added"


@outgoing
class MeetingInviteChanged(BaseObjectChanged):
    name = "meeting_invite.changed"


@outgoing
class MeetingInviteDeleted(BaseObjectDeleted):
    name = "meeting_invite.deleted"
