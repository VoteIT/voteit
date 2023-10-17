import rules

from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived
from voteit.room.permissions import RoomPermissions

rules.add_perm(RoomPermissions.ADD, meeting_not_archived & is_moderator)
rules.add_perm(RoomPermissions.VIEW, can_view_meeting)
rules.add_perm(RoomPermissions.CHANGE, meeting_not_archived & is_moderator)
rules.add_perm(RoomPermissions.DELETE, meeting_not_archived & is_moderator)
