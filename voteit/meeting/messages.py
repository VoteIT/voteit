from abc import ABC

from auditlog.context import set_actor
from pydantic import BaseModel
from pydantic import constr
from pydantic import validator
from envelope.core.message import ContextAction
from envelope.messages.common import ProgressNum
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import UnauthorizedError
from envelope.utils import websocket_send

from voteit.meeting.dialects import DialectHandler
from voteit.meeting.dialects import dialect_registry
from voteit.meeting.dialects import get_named_path_dict
from voteit.meeting.exceptions import DialectError
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.utils import clone_meeting
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted


@outgoing
class MeetingChanged(BaseObjectChanged):
    name = "meeting.changed"


@outgoing
class MeetingDeleted(BaseObjectDeleted):
    name = "meeting.deleted"


@outgoing
class MeetingGroupAdded(BaseObjectAdded):
    name = "meeting_group.added"


@outgoing
class MeetingGroupChanged(BaseObjectChanged):
    name = "meeting_group.changed"


@outgoing
class MeetingGroupDeleted(BaseObjectDeleted):
    name = "meeting_group.deleted"


@outgoing
class GroupRoleAdded(BaseObjectAdded):
    name = "group_role.added"


@outgoing
class GroupRoleChanged(BaseObjectChanged):
    name = "group_role.changed"


@outgoing
class GroupRoleDeleted(BaseObjectDeleted):
    name = "group_role.deleted"


@outgoing
class GroupMembershipAdded(BaseObjectAdded):
    name = "group_membership.added"


@outgoing
class GroupMembershipChanged(BaseObjectChanged):
    name = "group_membership.changed"


@outgoing
class GroupMembershipDeleted(BaseObjectDeleted):
    name = "group_membership.deleted"


class CopyMeetingSchema(BaseModel):
    meeting: int
    # Settings etc later on


@incoming
class CopyMeeting(ContextAction):
    name = "meeting.create_copy"
    permission = MeetingPermissions.VIEW
    schema = CopyMeetingSchema
    data: CopyMeetingSchema
    model = Meeting
    context_schema_attr = "meeting"

    def run_job(self):
        # Read meeting
        self.assert_perm()
        organisation = self.user.organisation
        assert organisation
        # Double permission check here, since add is needed too
        if not self.user.has_perm(MeetingPermissions.ADD, organisation):
            raise UnauthorizedError.from_message(
                self,
                model=organisation.__class__,
                key="pk",
                value=organisation.pk,
                permission=MeetingPermissions.ADD,
            )
        meeting: Meeting = self.context
        update = Status.from_message(self)
        websocket_send(update, state=update.RUNNING, on_commit=False)
        with set_actor(self.user):
            clone_meeting(meeting, user=self.user)
        websocket_send(update, state=update.SUCCESS)


class DialectSchema(BaseModel):
    dialect: constr(max_length=30, to_lower=True)
    meeting: int

    @validator("dialect")
    def validate_dialect(cls, v: str):
        """Very basic validation, we only check existing filename"""
        if v and v not in get_named_path_dict():
            raise ValueError(f"{v} is not a known meeting dialect name")
        return v


class DialectAction(ContextAction, ABC):
    permission = MeetingPermissions.CHANGE_DIALECT
    schema = DialectSchema
    data: DialectSchema
    model = Meeting
    context: Meeting
    context_schema_attr = "meeting"

    def get_handlers(self) -> list[DialectHandler]:
        self.assert_perm()
        try:
            return dialect_registry.get_dependent_dialects(self.data.dialect)
        except DialectError as exc:
            # Other exc?
            raise BadRequestError.from_message(self, msg=str(exc))


@incoming
class InstallDialect(DialectAction):
    name = "meeting_dialect.install"

    def run_job(self):
        if self.context.installed_dialects is not None:
            raise BadRequestError.from_message(
                self, msg="This meeting already has an installed dialect"
            )
        #        websocket_send(update, state=update.RUNNING, on_commit=False)
        handlers = self.get_handlers()
        if not handlers[0].data.installable:
            raise BadRequestError.from_message(
                self, msg="This dialect isn't installable"
            )
        i = 0
        total = len(handlers)
        with set_actor(self.user):
            for handler in reversed(
                handlers
            ):  # <- required dialects must be installed first
                websocket_send(
                    ProgressNum.from_message(self, curr=i, total=total),
                    state=self.RUNNING,
                    on_commit=False,
                )
                handler.install(self.context)
                i += 1
        result = ProgressNum.from_message(
            self, curr=i, total=total, msg=f"Installed f{self.data.dialect}"
        )
        websocket_send(result, state=self.SUCCESS)
        return result


@incoming
class RemoveDialect(DialectAction):
    name = "meeting_dialect.remove"

    def run_job(self):
        if self.context.installed_dialects is None:
            raise BadRequestError.from_message(self, msg="Nothing installed")
        handlers = self.get_handlers()
        installed = self.context.installed_dialects.split(",")
        handler_names = [x.data.name for x in reversed(handlers)]
        if handler_names != installed:
            raise BadRequestError.from_message(
                self,
                msg=f"This is not the installed dialect, or installation has changed some how. "
                f"Installed: {','.join(installed)} Removal: {','.join(handler_names)}",
            )
        total = len(handlers)
        i = 0
        with set_actor(self.user):
            for handler in handlers:
                websocket_send(
                    ProgressNum.from_message(self, curr=i, total=total),
                    state=self.RUNNING,
                    on_commit=False,
                )
                handler.remove(self.context)
                i += 1
        result = ProgressNum.from_message(
            self, curr=i, total=total, msg=f"Removed f{self.data.dialect}"
        )
        websocket_send(result, state=self.SUCCESS)
        return result
