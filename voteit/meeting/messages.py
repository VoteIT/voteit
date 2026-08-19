from typing import Literal
from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class MeetingChanged(ObjectAddedOrChanged):
    action: Literal["meeting.changed"] = "meeting.changed"


@outgoing
class MeetingDeleted(ObjectDeleted):
    action: Literal["meeting.deleted"] = "meeting.deleted"


@outgoing
class MeetingDialectChanged(ObjectAddedOrChanged):
    action: Literal["meeting.dialect_changed"] = "meeting.dialect_changed"


@outgoing
class MeetingGroupChanged(ObjectAddedOrChanged):
    action: Literal["meeting_group.changed"] = "meeting_group.changed"


@outgoing
class MeetingGroupDeleted(ObjectDeleted):
    action: Literal["meeting_group.deleted"] = "meeting_group.deleted"


@outgoing
class GroupRoleChanged(ObjectAddedOrChanged):
    action: Literal["group_role.changed"] = "group_role.changed"


@outgoing
class GroupRoleDeleted(ObjectDeleted):
    action: Literal["group_role.deleted"] = "group_role.deleted"


@outgoing
class GroupMembershipChanged(ObjectAddedOrChanged):
    action: Literal["group_membership.changed"] = "group_membership.changed"


@outgoing
class GroupMembershipDeleted(ObjectDeleted):
    action: Literal["group_membership.deleted"] = "group_membership.deleted"
