from __future__ import annotations

from functools import cached_property
from logging import getLogger
from typing import TYPE_CHECKING

from auditlog.context import set_actor
from django.db import transaction
from envelope.core.message import ContextAction
from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.utils import websocket_send

from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.schemas import AddMixedUserDataInvitesSchema
from voteit.invites.schemas import AddInviteAnnotationsSchema
from voteit.invites.schemas import AnnotationResultSchema
from voteit.invites.schemas import InvitesResultSchema
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.models import Meeting
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing

if TYPE_CHECKING:
    from voteit.invites.registries import InviteAdapterRegistry

logger = getLogger(__name__)


@incoming
class AddInvites(ContextAction):
    name = "invites.add"
    permission = MeetingInvitePermissions.ADD
    schema = AddMixedUserDataInvitesSchema
    data: AddMixedUserDataInvitesSchema
    model = Meeting
    context_schema_attr = "meeting"
    job_timeout = 40
    atomic = False

    @cached_property
    def invite_data_reg(self) -> InviteAdapterRegistry:
        return get_invite_adapter_registry()

    def run_job(self) -> InvitesAdded:
        self.assert_perm()
        self.validate()  # FIXME
        items = list(
            self.invite_data_reg.build_ud_query_seq(self.data.columns, self.data.rows)
        )
        existing_qs, partial = self.context.invites.find_mixed_user_data(*items)
        if partial:
            msg = "Found partial matches, aborting. Matched types:\n"
            for k, v in partial.items():
                msg += f"{k}: {v.count()}\n"
            raise BadRequestError.from_message(
                self,
                msg=msg,
            )
        # FIXME: How do we handle longer rows? Do we need to kill msg because of it?
        with set_actor(self.user):
            with transaction.atomic(durable=True):
                result = self.context.invites.create_or_update_mixed(
                    data=items, roles=self.data.roles, meeting=self.context
                )
                if self.data.dryrun:
                    transaction.set_rollback(True)
        response = InvitesAdded.from_message(
            self,
            added=result.added,
            changed=result.changed,
            existed=result.existed,
        )
        if response.mm.consumer_name:  # In case it was run by a script
            websocket_send(response, state=response.SUCCESS)
        return response


@incoming
class AddInviteAnnotations(ContextAction):
    name = "invites.add_annotations"
    permission = MeetingInvitePermissions.ADD
    schema = AddInviteAnnotationsSchema
    data: AddInviteAnnotationsSchema
    model = Meeting
    context_schema_attr = "meeting"
    job_timeout = 40
    atomic = False

    @cached_property
    def invite_data_reg(self) -> InviteAdapterRegistry:
        return get_invite_adapter_registry()

    def run_job(self) -> list[AnnotationResult, None]:
        self.assert_perm()
        self.validate()  # FIXME
        items = list(
            self.invite_data_reg.build_ud_query_seq(self.data.columns, self.data.rows)
        )
        existing_qs, partial = self.context.invites.find_mixed_user_data(*items)
        if partial:
            msg = "Found partial matches, aborting. Matched types:\n"
            for k, v in partial:
                msg += f"{k}: {v.count()}\n"
            raise BadRequestError.from_message(
                self,
                msg=msg,
            )
        try:
            self.invite_data_reg.run_validators(
                self.data.columns, self.data.rows, meeting=self.context
            )
        except ValueError as exc:
            raise BadRequestError.from_message(
                self,
                msg=str(exc),
            )
        results = []
        with set_actor(self.user):
            with transaction.atomic(durable=True):
                for annotation_result in self.invite_data_reg.run_annotations(
                    columns=self.data.columns,
                    rows=self.data.rows,
                    invites_qs=existing_qs,
                    meeting=self.context,
                ):
                    if annotation_result is None:
                        results.append(None)
                    else:
                        msg = AnnotationResult.from_message(
                            self, data=annotation_result.dict()
                        )
                        results.append(msg)
                        if msg.mm.consumer_name:  # In case it was run by a script
                            websocket_send(msg, state=self.RUNNING, on_commit=False)
                if self.data.dryrun:
                    transaction.set_rollback(True)
        response = Status.from_message(self)
        if response.mm.consumer_name:  # In case it was run by a script
            websocket_send(response, state=response.SUCCESS)
        return results


@outgoing
class InvitesAdded(Message):
    name = "invites.added"
    schema = InvitesResultSchema
    data: InvitesResultSchema


@outgoing
class AnnotationResult(Message):
    name = "invites.annotation"
    schema = AnnotationResultSchema
    data: AnnotationResultSchema


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
