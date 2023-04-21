from __future__ import annotations
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils.timezone import now

from envelope.models import Connection
from voteit.active.components import ActiveUsersComponent
from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from voteit.active.models import ActiveUser


def active_enabled_for_meeting(meeting: Meeting) -> bool:
    return meeting.components.filter(
        component_name=ActiveUsersComponent.name, state=EnabledWf.ON
    ).exists()


def get_inactive_qs(meeting: Meeting, hours: int = 2) -> QuerySet[ActiveUser]:
    recent_enough_connections_qs = Connection.objects.filter(
        last_action__gt=now() - timedelta(hours=hours),
    )
    return meeting.active_users.exclude(
        user_id__in=recent_enough_connections_qs.values_list("user_id")
    )
