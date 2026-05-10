from __future__ import annotations

from datetime import timedelta
from logging import getLogger

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.timezone import now

from voteit.core.decorators import schedule_job


logger = getLogger(__name__)
User = get_user_model()


@schedule_job("35 04 * * 1")
def deactivate_unused_users() -> int:
    """
    Deactivates users if:
    - More than 30 days since last_login (or never logged in)
    - No MeetingRoles and no OrganisationRoles

    Returns count of deactivated users.
    """
    cutoff = now() - timedelta(days=30)
    count = (
        User.objects.filter(is_active=True)
        .filter(Q(last_login__lt=cutoff) | Q(last_login__isnull=True))
        .filter(meeting_roles__isnull=True)
        .filter(organisation_roles__isnull=True)
        .update(is_active=False)
    )
    logger.info("deactivate_unused_users: deactivated %d users", count)
    return count
