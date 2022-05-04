from __future__ import annotations

import rules

from voteit.access_policy.permissions import AutomaticAccessPermissions
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived

rules.add_perm(AutomaticAccessPermissions.ADD, meeting_not_archived & is_moderator)
rules.add_perm(AutomaticAccessPermissions.VIEW, is_moderator)
rules.add_perm(AutomaticAccessPermissions.CHANGE, meeting_not_archived & is_moderator)
rules.add_perm(AutomaticAccessPermissions.DELETE, meeting_not_archived & is_moderator)
