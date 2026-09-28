from __future__ import annotations

from datetime import timedelta
from logging import getLogger

from django.utils.timezone import now

from voteit.core.decorators import schedule_job
from voteit.meeting.models import Meeting
from voteit.meeting.statemachines import MeetingStateMachine

logger = getLogger(__name__)

#: Grace period, so abort_delete is still possible for a while.
DELETE_AFTER_DAYS = 7


@schedule_job("10 05 * * 2")
def delete_requested_meetings() -> int:
    """
    Delete meetings that never started and have been in state deleting
    for more than DELETE_AFTER_DAYS.
    """
    count = 0
    qs = Meeting.objects.filter(
        state=MeetingStateMachine.deleting.value,
        start_time__isnull=True,
        delete_requested__lt=now() - timedelta(days=DELETE_AFTER_DAYS),
    )
    for meeting in qs:
        logger.info(
            "delete_requested_meetings: deleting meeting %d %r (organisation %s)",
            meeting.pk,
            meeting.title,
            meeting.organisation_id,
        )
        meeting.delete()
        count += 1
    return count
