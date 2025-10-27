from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django_rq import get_queue
from fakeredis import FakeRedis
from rq.registry import ScheduledJobRegistry


def my_count_job(*args, **kwargs):
    return 1 + 1


class ScheduleTests(TestCase):
    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "schedule_job",
            *args,
            stdout=out,
            **kwargs,
        )
        return out.getvalue()

    def test_schedule_job(self):
        connection = FakeRedis()
        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=connection,
        ):
            self.call_command(
                "voteit.core.management.tests.test_schedule_jobs.my_count_job",
                "2025-10-27 10:30",
            )

        queue = get_queue(connection=connection)
        scheduler_registry = ScheduledJobRegistry(
            queue=queue, connection=queue.connection
        )
        self.assertEqual(1, len(scheduler_registry))
        job_id = scheduler_registry.get_job_ids()[0]
        ts = scheduler_registry.get_scheduled_time(job_id)
        # UTC TZ here!
        self.assertEqual("2025-10-27T09:30", ts.isoformat()[:16])

    def test_schedule_job_duplicate(self):
        connection = FakeRedis()
        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=connection,
        ):
            self.call_command(
                "voteit.core.management.tests.test_schedule_jobs.my_count_job",
                "2025-10-27 10:30",
            )
            self.call_command(
                "voteit.core.management.tests.test_schedule_jobs.my_count_job",
                "2025-10-27 11:00",
            )

        queue = get_queue(connection=connection)
        scheduler_registry = ScheduledJobRegistry(
            queue=queue, connection=queue.connection
        )
        self.assertEqual(1, len(scheduler_registry))
        job_id = scheduler_registry.get_job_ids()[0]
        ts = scheduler_registry.get_scheduled_time(job_id)
        # UTC TZ here!
        self.assertEqual("2025-10-27T09:30", ts.isoformat()[:16])
