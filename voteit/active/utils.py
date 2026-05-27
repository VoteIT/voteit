from __future__ import annotations
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils.timezone import now

from envelope.models import Connection
from voteit.active.components import ActiveUsersComponent
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from voteit.active.models import ActiveUser


def active_enabled_for_meeting(meeting: Meeting) -> bool:
    return meeting.component_enabled(ActiveUsersComponent.name)


def get_inactive_qs(meeting: Meeting, hours: int = 1) -> QuerySet[ActiveUser]:
    # Setting 0 will remove every last one, even connected, so we use 5 mins instead
    if hours:
        timestamp = now() - timedelta(hours=hours)
    else:
        timestamp = now() - timedelta(minutes=5)
    recent_enough_connections_qs = Connection.objects.filter(
        last_action__gt=timestamp,
    )
    return meeting.active_users.exclude(
        user_id__in=recent_enough_connections_qs.values_list("user_id")
    )
