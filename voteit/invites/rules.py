from __future__ import annotations

import rules

from voteit.invites.permissions import MeetingInvitePermissions
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived

# Add Checked against meeting
rules.add_perm(MeetingInvitePermissions.ADD, is_moderator & meeting_not_archived)
rules.add_perm(MeetingInvitePermissions.CHANGE, is_moderator & meeting_not_archived)
rules.add_perm(MeetingInvitePermissions.DELETE, is_moderator & meeting_not_archived)
rules.add_perm(MeetingInvitePermissions.VIEW, is_moderator)
