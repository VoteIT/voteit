from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
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
