from auditlog.context import set_actor
from pydantic import BaseModel

from envelope.core.message import ContextAction
from envelope.messages.common import Status
from envelope.messages.errors import UnauthorizedError
from envelope.utils import websocket_send
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.utils import clone_meeting
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing


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
