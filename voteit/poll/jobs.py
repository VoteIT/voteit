from __future__ import annotations

from datetime import timedelta
from logging import getLogger

import django_rq
from django.conf import settings
from redis.exceptions import ConnectionError
from redis.exceptions import TimeoutError
from rq.job import Job

from voteit.core import RQ_DEFAULT_QUEUE
from voteit.meeting.channels import MeetingChannel
from voteit.poll.messages import PollStatus
from voteit.poll.models import Poll

logger = getLogger(__name__)


def _poll_status_job_id(poll_pk: int) -> str:
    # RQ job IDs may only contain letters, numbers, underscores and dashes.
    return f"poll-status-{poll_pk}"


def publish_poll_status(poll_pk: int) -> None:
    """
    RQ job body - also called directly (synchronously) as a fallback when
    Redis/RQ is unreachable at schedule time. Re-fetches the Poll so it
    always reads the freshest vote count, regardless of how long the job
    sat queued.
    """
    try:
        poll = Poll.objects.select_related("electoral_register").get(pk=poll_pk)
    except Poll.DoesNotExist:
        logger.info("publish_poll_status: poll %s no longer exists, skipping", poll_pk)
        return
    if poll.meeting_id is None:
        return
    if poll.electoral_register_id is None:
        # Race: ER was detached (SET_NULL) between vote and job execution.
        logger.info(
            "publish_poll_status: poll %s has no electoral register, skipping",
            poll_pk,
        )
        return
    msg = PollStatus(
        pk=poll.pk,
        voted=poll.votes.count(),
        total=len(poll.electoral_register.voter_data),
    )
    MeetingChannel(poll.meeting_id).sync_publish(msg)


def schedule_poll_status_publish(poll_pk: int) -> None:
    """
    Throttled scheduling: if a publish job for this poll is already
    pending, do nothing (it will read the current vote count when it
    runs). Otherwise schedule one settings.POLL_STATUS_THROTTLE_SECONDS
    seconds from now.

    Must be called from within (or after) transaction.on_commit - the RQ
    worker re-fetches the Poll/Vote rows from the DB in a separate
    connection/process, so it must not run before the triggering vote is
    actually committed.
    """
    job_id = _poll_status_job_id(poll_pk)
    queue = django_rq.get_queue(RQ_DEFAULT_QUEUE)
    try:
        if not Job.exists(job_id, connection=queue.connection):
            queue.enqueue_in(
                timedelta(seconds=settings.POLL_STATUS_THROTTLE_SECONDS),
                publish_poll_status,
                poll_pk,
                job_id=job_id,
                job_timeout=30,
                result_ttl=0,
                ttl=60,
                failure_ttl=60,
            )
    except (ConnectionError, TimeoutError):
        logger.warning(
            "Redis unreachable scheduling poll status publish for poll %s, "
            "publishing synchronously instead",
            poll_pk,
        )
        publish_poll_status(poll_pk)
