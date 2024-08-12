from datetime import datetime
from datetime import timedelta
from logging import getLogger

from django.utils.timezone import now
from django_rq import get_queue
from rq.registry import ScheduledJobRegistry

from voteit.invites.models import MeetingInvite
from voteit.invites.workflows import InviteWf

logger = getLogger(__name__)


def get_expire_job_id(timestamp: datetime) -> str:
    return f"invite_expire_{timestamp.isoformat()[:10]}"


def _requeue_next(*args, **kwargs):
    add_to_queue_if_needed(**kwargs)


def add_to_queue_if_needed(timestamp: datetime | None = None, **kwargs):
    queue = get_queue(**kwargs)
    registry = ScheduledJobRegistry(queue=queue, connection=queue.connection)
    if timestamp is None:
        timestamp = now() + timedelta(days=1)
        timestamp = datetime(timestamp.year, timestamp.month, timestamp.day, 4, 0)
    job_id = get_expire_job_id(timestamp)
    if job_id in registry:
        logger.debug("Won't reschedule job %s since it already existed", job_id)
    else:
        logger.debug("Scheduling %s at %s", job_id, timestamp)
        return queue.enqueue_at(
            timestamp,
            expire_unused_invites,
            job_id=job_id,
            on_failure=_requeue_next,
            on_success=_requeue_next,
        )


def expire_unused_invites() -> int:
    """
    Expire invites if:
    - Meeting was closed more than 3 days ago
    - Invite was created more than 3 days ago and is open
    (invites for closed meetings is still a valid usecase!)
    """
    invites_qs = MeetingInvite.objects.should_expire()
    # We don't care about transition here
    return invites_qs.update(state=InviteWf.EXPIRED)
