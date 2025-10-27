from __future__ import annotations

from datetime import datetime

from django.core.management import BaseCommand
from django.utils.timezone import get_current_timezone
from rq.utils import import_attribute

from voteit.core.jobs import add_periodic_job


def _get_dt_with_tz(value) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(
        tzinfo=get_current_timezone()
    )


class Command(BaseCommand):
    help = "Schedule a job to be run at a specific time"

    def add_arguments(self, parser):
        parser.add_argument(
            "func",
            type=import_attribute,
            help="Function to schedule, dotted path",
        )
        parser.add_argument(
            "timestamp",
            help="When the job should be scheduled the first time, specified as YY-MM-DD HH:MM",
            type=_get_dt_with_tz,
        )
        parser.add_argument(
            "--now",
            action="store_true",
            help="Run right now too",
        )
        parser.add_argument(
            "--days",
            help="Repeat interval in days, default 1. If 0, job won't be rescheduled",
            type=int,
            default=1,
        )

    def handle(self, *args, **options):
        timestamp = options.get("timestamp")
        func = options.get("func")
        if job := add_periodic_job(
            func,
            timestamp=timestamp,
            days=options.get("days"),
            immediate=options.get("now"),
        ):
            self.stdout.write("Created job {}".format(job.id))
        else:
            self.stdout.write("No new job created, perhaps there was one?")
