from __future__ import annotations

from typing import TYPE_CHECKING

import rules
from django.contrib.auth.models import AbstractUser

from voteit.access_policy.permissions import MeetingInvitePermissions
from voteit.access_policy.workflows import InviteWf
from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived
from voteit.meeting.rules import is_moderator

if TYPE_CHECKING:
    from voteit.access_policy.models import MeetingInvite


@predicate
def is_state_open(user: AbstractUser, instance: MeetingInvite) -> bool:
    """Generic check for archived state.
    Keep this as a negated state since check for is not None will return a false positive otherwise!
    """
    state = getattr(instance, "state", None)
    return state == InviteWf.OPEN


rules.add_perm(
    MeetingInvitePermissions.ADD, is_moderator & is_not_archived
)  # Checked against meeting.
rules.add_perm(MeetingInvitePermissions.CHANGE, is_moderator & is_state_open)
rules.add_perm(MeetingInvitePermissions.DELETE, is_moderator & is_state_open)
rules.add_perm(MeetingInvitePermissions.VIEW, is_moderator)
