from __future__ import annotations

import rules

from voteit.access_policy.app.policies import AutomaticAccess
from voteit.core import PERM
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived

rules.add_perm(AutomaticAccess.get_perm(PERM.ADD), meeting_not_archived & is_moderator)
rules.add_perm(
    AutomaticAccess.get_perm(PERM.CHANGE), meeting_not_archived & is_moderator
)
rules.add_perm(
    AutomaticAccess.get_perm(PERM.DELETE), meeting_not_archived & is_moderator
)
