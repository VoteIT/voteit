from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils.timezone import now
from django_rq import get_queue
from fakeredis import FakeRedis
from rq import SimpleWorker
from rq.registry import ScheduledJobRegistry

from voteit.core.jobs import add_periodic_job


def my_count_job(*args, **kwargs):
    return 1 + 1


class PeriodicJobTests(TestCase):
    def test_add_job_enters_queue(self):
        connection = FakeRedis()
        queue = get_queue(connection=connection)
        ts = now() + timedelta(days=1)
        add_periodic_job(my_count_job, queue=queue, timestamp=ts)
        registry = ScheduledJobRegistry(queue=queue, connection=queue.connection)
        job_ids = registry.get_job_ids()
        self.assertEqual(1, len(job_ids))
        job = queue.fetch_job(job_ids[0])
        requested_ts = job.get_meta().get("requested_ts")
        self.assertEqual(requested_ts, ts)

    def test_add_immediate_schedules_for_tomorrow(self):
        connection = FakeRedis()
        queue = get_queue(connection=connection)
        scheduler_registry = ScheduledJobRegistry(
            queue=queue, connection=queue.connection
        )
        self.assertEqual(0, len(scheduler_registry))
        initial_ts = now()

        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=connection,
        ):
            add_periodic_job(
                my_count_job, immediate=True, queue=queue, timestamp=initial_ts
            )
            worker = SimpleWorker([queue], connection=queue.connection)
            self.assertTrue(worker.work(burst=True))

        self.assertEqual([], queue.get_jobs())
        # Tomorrows´ job
        self.assertEqual(1, len(scheduler_registry))
        job_id = scheduler_registry.get_job_ids()[0]
        ts = scheduler_registry.get_scheduled_time(job_id)
        self.assertEqual((initial_ts + timedelta(days=1)).day, ts.day)
        self.assertEqual(ts.minute, initial_ts.minute)
        self.assertEqual(ts.hour, initial_ts.hour)
        # Readding a job won't have any effect
        add_periodic_job(my_count_job, queue=queue, timestamp=ts)
        self.assertEqual(1, len(scheduler_registry))

    def test_add_immediate_but_only_one_run(self):
        connection = FakeRedis()
        queue = get_queue(connection=connection)
        scheduler_registry = ScheduledJobRegistry(
            queue=queue, connection=queue.connection
        )
        self.assertEqual(0, len(scheduler_registry))
        initial_ts = now()

        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=connection,
        ):
            add_periodic_job(
                my_count_job, immediate=True, queue=queue, timestamp=initial_ts, days=0
            )
            worker = SimpleWorker([queue], connection=queue.connection)
            self.assertTrue(worker.work(burst=True))

        self.assertEqual([], queue.get_jobs())
        # Tomorrows´ job
        self.assertEqual(0, len(scheduler_registry))
