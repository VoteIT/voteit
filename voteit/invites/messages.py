from __future__ import annotations

from functools import cached_property
from logging import getLogger
from typing import TYPE_CHECKING

from auditlog.context import set_actor
from django.db import transaction
from django.utils.translation import gettext as _
from envelope.deferred_jobs.message import ContextAction
from envelope.core.message import Message
from envelope.messages.common import ProgressNum
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.utils import websocket_send

from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.schemas import AddMixedUserDataInvitesSchema
from voteit.invites.schemas import AddInviteAnnotationsSchema
from voteit.invites.schemas import AnnotationResultSchema
from voteit.invites.schemas import ClearInviteAnnotationsSchema
from voteit.invites.schemas import InvitesResultSchema
from voteit.invites.utils import get_invite_adapter_registry
from voteit.invites.utils import send_updated_invites
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
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
        items = list(
            self.invite_data_reg.build_ud_query_seq(self.data.columns, self.data.rows)
        )
        existing_qs, conflicting_partials = self.context.invites.find_mixed_user_data(
            *items
        )
        if conflicting_partials:
            msg = _(
                "Found existing invites matching only parts of a row. "
                "Look for rows containing the following items:"
            )
            msg += " \n"
            for k, v in conflicting_partials.items():
                msg += _("Column %(k)s:") % {"k": k}
                msg += " \n"
                for ud in v.values_list("user_data", flat=True)[:5]:
                    msg += f"{ud.get(k)}\n"
            raise BadRequestError.from_message(
                self,
                msg=msg,
            )
        # Protect against dumb lockout
        if ROLE_MODERATOR not in self.data.roles:
            curr_moderators = self.context.roles.filter(
                assigned__contains=ROLE_MODERATOR
            ).values_list("user", flat=True)
            moderators = existing_qs.filter(used_by__in=curr_moderators)
            if moderators:
                items = [
                    ", ".join(x.values())
                    for x in moderators.values_list("user_data", flat=True)
                ]
                msg = _(
                    "Your action would downgrade permissions for some moderators. "
                    "Handle moderators via participants tab instead. "
                    "Related to userID(s): %(userids)s. Data: %(data)s"
                ) % {
                    "userids": ", ".join(
                        moderators.values_list("used_by__userid", flat=True)
                    ),
                    "data": "\n".join(items),
                }
                raise BadRequestError.from_message(
                    self,
                    msg=msg,
                )
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

    def run_job(self) -> list[AnnotationResult | None]:
        self.assert_perm()
        items = list(
            self.invite_data_reg.build_ud_query_seq(self.data.columns, self.data.rows)
        )
        existing_qs, conflicting_partials = self.context.invites.find_mixed_user_data(
            *items
        )
        if conflicting_partials:
            msg = _(
                "Found existing invites matching only parts of a row. "
                "Look for rows containing the following items:"
            )
            msg += " \n"
            for k, v in conflicting_partials.items():
                msg += _("Column %(k)s:") % {"k": k}
                msg += " \n"
                for ud in v.values_list("user_data", flat=True)[:5]:
                    msg += f"{ud.get(k)}\n"
            raise BadRequestError.from_message(
                self,
                msg=msg,
            )
        invite_data = list(existing_qs.values_list("user_data", flat=True))
        bad_row = []
        for item in items:
            if item not in invite_data:
                bad_row.append(item)
        if bad_row:
            msg = _(
                "The following don't match any existing invites. "
                "Perhaps the invite doesn't exist or were only partially matched? "
                "Look for the following data:"
            )
            msg += " \n"
            for bad in bad_row[:5]:
                msg += ",".join(bad.values())
                msg += " \n"
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
                invite_pks_to_signal = set()
                # FIXME: We need to send signal for annotated invites too
                total_ann_count = sum(
                    x.is_runnable
                    for x in self.invite_data_reg.get_annotations(
                        columns=self.data.columns
                    )
                )
                initial_msg = ProgressNum.from_message(
                    self, curr=0, total=total_ann_count
                )
                if initial_msg.mm.consumer_name:  # In case it was run by a script
                    websocket_send(
                        initial_msg, state=initial_msg.RUNNING, on_commit=False
                    )
                for i, annotation_result in enumerate(
                    self.invite_data_reg.run_annotations(
                        columns=self.data.columns,
                        rows=self.data.rows,
                        invites_qs=existing_qs,
                        meeting=self.context,
                    ),
                    1,
                ):
                    if annotation_result is None:
                        results.append(None)
                    else:
                        annotation_result.curr = i
                        annotation_result.total = total_ann_count
                        msg = AnnotationResult.from_message(
                            self, data=annotation_result.dict()
                        )
                        results.append(msg)
                        if msg.mm.consumer_name:  # In case it was run by a script
                            websocket_send(msg, state=self.RUNNING, on_commit=False)
                        if annotation_result.newly_annotated_invites:
                            invite_pks_to_signal.update(
                                annotation_result.newly_annotated_invites
                            )
                if self.data.dryrun:
                    transaction.set_rollback(True)
                else:
                    send_updated_invites(
                        self.context,
                        self.context.invites.filter(pk__in=invite_pks_to_signal),
                        annotate=True,
                    )
            # FIXME Send signal in case of commit
        response = Status.from_message(self)
        if response.mm.consumer_name:  # In case it was run by a script
            websocket_send(response, state=response.SUCCESS)
        return results


@incoming
class ClearInviteAnnotations(ContextAction):
    name = "invites.clear_annotations"
    permission = MeetingInvitePermissions.ADD
    schema = ClearInviteAnnotationsSchema
    data: ClearInviteAnnotationsSchema
    model = Meeting
    context_schema_attr = "meeting"
    job_timeout = 30
    atomic = True

    @cached_property
    def invite_data_reg(self) -> InviteAdapterRegistry:
        return get_invite_adapter_registry()

    def run_job(self):
        self.assert_perm()
        with set_actor(self.user):
            invites_qs = self.invite_data_reg.clear(self.context, *self.data.types)
            send_updated_invites(self.context, invites_qs, annotate=False)
        response = Status.from_message(self)
        if response.mm.consumer_name:  # In case it was run by a script
            websocket_send(response, state=response.SUCCESS)
        return invites_qs


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


@outgoing
class MeetingInviteAdded(BaseObjectAdded):
    name = "meeting_invite.added"


@outgoing
class MeetingInviteChanged(BaseObjectChanged):
    name = "meeting_invite.changed"


@outgoing
class MeetingInviteDeleted(BaseObjectDeleted):
    name = "meeting_invite.deleted"
