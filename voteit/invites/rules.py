from __future__ import annotations

import rules

from voteit.core import PERM
from voteit.invites.models import MeetingInvite
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived

# Add Checked against meeting
rules.add_perm(MeetingInvite.get_perm(PERM.ADD), is_moderator & meeting_not_archived)
rules.add_perm(MeetingInvite.get_perm(PERM.CHANGE), is_moderator & meeting_not_archived)
rules.add_perm(MeetingInvite.get_perm(PERM.DELETE), is_moderator & meeting_not_archived)
