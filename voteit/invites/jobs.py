from __future__ import annotations

from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING

from django.utils.timezone import now
from voteit.core.decorators import schedule_job
from voteit.invites.models import MeetingInvite
from voteit.invites.workflows import InviteWf

if TYPE_CHECKING:
    pass


logger = getLogger(__name__)


@schedule_job("30 3 * * *")
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


@schedule_job("50 3 * * *")
def cleanup_invites():
    """
    - 200 days from modification date
    - 30 days for expired invites
    """
    # There's really no reason to keep this around longer
    expired_revoked_qs = MeetingInvite.objects.filter(
        state__in=[InviteWf.EXPIRED, InviteWf.REVOKED],
        modified__lt=now() - timedelta(days=30),
    )
    expired_revoked_count = expired_revoked_qs.count()
    expired_revoked_qs.delete()
    # Other invite states may be deleted too, lets set 6 months to be on the safe side
    other_states_qs = MeetingInvite.objects.filter(
        modified__lt=now() - timedelta(days=200),
    )
    other_states_count = other_states_qs.count()
    other_states_qs.delete()
    return {
        "expired_revoked_count": expired_revoked_count,
        "other_states_count": other_states_count,
    }
