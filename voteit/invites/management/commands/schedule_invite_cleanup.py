from __future__ import annotations

from django.core.management import BaseCommand
from django.utils.timezone import now

from voteit.invites.jobs import add_to_queue_if_needed


class Command(BaseCommand):
    help = "Schedule invite cleanup"

    def add_arguments(self, parser):
        parser.add_argument(
            "--now",
            action="store_true",
            help="Schedule run right away - will also schedule upcoming runs if there are any",
        )

    def handle(self, *args, **options):
        timestamp = None
        if options.get("now"):
            timestamp = now()
        if job := add_to_queue_if_needed(timestamp=timestamp):
            self.stdout.write(f"Added job {job.id} from {job.func_name}")
        else:
            self.stdout.write("Invites expire job already existed")
