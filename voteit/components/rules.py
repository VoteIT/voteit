from __future__ import annotations

import rules

from voteit.components.permissions import MeetingComponentPermissions
from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived


rules.add_perm(MeetingComponentPermissions.ADD, meeting_not_archived & is_moderator)
rules.add_perm(MeetingComponentPermissions.VIEW, can_view_meeting)
rules.add_perm(MeetingComponentPermissions.CHANGE, meeting_not_archived & is_moderator)
rules.add_perm(MeetingComponentPermissions.DELETE, meeting_not_archived & is_moderator)
