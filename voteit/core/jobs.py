from __future__ import annotations
from datetime import datetime
from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING

from django_rq import get_queue
from rq.registry import ScheduledJobRegistry


if TYPE_CHECKING:
    from rq.job import Job
logger = getLogger(__name__)


def _requeue_from_job(job: Job, *args, **kwargs):
    meta = job.get_meta()
    if "requested_ts" in meta:
        if days := meta.get("days"):
            tiemstamp = meta["requested_ts"] + timedelta(days=days)
            add_periodic_job(job.func, timestamp=tiemstamp)
        else:
            logger.warning(f"Days set to 0 so won't reschedule {job.func_name}")
    else:
        logger.warning(f"No requested timestamp for {job.func_name}")


def add_periodic_job(func, queue=None, immediate=False, *, timestamp: datetime, days=1):
    if queue is None:
        queue = get_queue("default")
    registry = ScheduledJobRegistry(queue=queue, connection=queue.connection)
    job_id = f"{func.__name__}_{timestamp.isoformat()[:10]}"
    meta = {"requested_ts": timestamp, "days": days}
    if job_id in registry:
        logger.debug("Won't reschedule job %s since it already existed", job_id)
    else:
        if immediate:
            logger.debug("Running chores immediately, id %s", job_id)
            return queue.enqueue(
                func,
                job_id=job_id,
                meta=meta,
                on_failure=_requeue_from_job,
                on_success=_requeue_from_job,
            )
        else:
            logger.debug("Scheduling %s at %s", job_id, timestamp)
            return queue.enqueue_at(
                timestamp,
                func,
                meta=meta,
                job_id=job_id,
                on_failure=_requeue_from_job,
                on_success=_requeue_from_job,
            )
