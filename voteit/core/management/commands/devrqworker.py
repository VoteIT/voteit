import shlex
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from watchfiles import PythonFilter
from watchfiles import run_process

# Same directories uvicorn reloads on in `make run`.
WATCH_DIRS = ("voteit", "project", "src")


class Command(BaseCommand):
    help = "Run rqworker and restart it when Python files change (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--with-scheduler", action="store_true")
        parser.add_argument("queues", nargs="*")

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        cmd = [sys.executable, str(base_dir / "manage.py"), "rqworker"]
        if options["with_scheduler"]:
            cmd.append("--with-scheduler")
        cmd.extend(options["queues"])
        # run_process stops the worker (SIGINT, then SIGKILL) and waits for it
        # before starting the next one, and also on SIGTERM / Ctrl+C, so no
        # worker outlives this command.
        run_process(
            *(base_dir / d for d in WATCH_DIRS if (base_dir / d).is_dir()),
            target=shlex.join(cmd),
            target_type="command",
            watch_filter=PythonFilter(),
            callback=lambda changes: self.stdout.write(
                "Changes detected, restarting rqworker"
            ),
        )
