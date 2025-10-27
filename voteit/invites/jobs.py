from __future__ import annotations
from logging import getLogger
from typing import TYPE_CHECKING

from voteit.invites.models import MeetingInvite
from voteit.invites.workflows import InviteWf

if TYPE_CHECKING:
    pass


logger = getLogger(__name__)


def expire_unused_invites() -> int:
    """
    Expire invites if:
    - Meeting was closed more than 3 days ago
    - Invite was created more than 3 days ago and is open
    (invites for closed meetings is still a valid use case!)
    """
    invites_qs = MeetingInvite.objects.should_expire()
    # We don't care about transition here
    return invites_qs.update(state=InviteWf.EXPIRED)
