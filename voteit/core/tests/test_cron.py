from django.test import SimpleTestCase
from django_rq.cron import DjangoCronScheduler

from voteit.core.decorators import scheduled_jobs


class CronConfigTests(SimpleTestCase):
    def test_rqcron_loads_every_scheduled_job(self):
        # Same path as `manage.py rqcron voteit.core.cron`, minus start().
        scheduler = DjangoCronScheduler()
        scheduler.load_config_from_file("voteit.core.cron")
        jobs = scheduler.get_jobs()
        self.assertTrue(scheduled_jobs)
        self.assertEqual(
            {j.func for j in jobs},
            {x["func"] for x in scheduled_jobs},
        )
        cleanup = next(j for j in jobs if j.func.__name__ == "cleanup_invites")
        self.assertEqual("long", cleanup.queue_name)
        self.assertEqual(600, cleanup.job_options["job_timeout"])

    def test_loading_twice_does_not_duplicate(self):
        scheduler = DjangoCronScheduler()
        scheduler.load_config_from_file("voteit.core.cron")
        scheduler = DjangoCronScheduler()
        scheduler.load_config_from_file("voteit.core.cron")
        self.assertEqual(len(scheduled_jobs), len(scheduler.get_jobs()))
