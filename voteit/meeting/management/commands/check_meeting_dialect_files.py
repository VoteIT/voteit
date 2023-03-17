from __future__ import annotations

import sys

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import BaseCommand

from voteit.meeting.dialects import check_dialect_files


class Command(BaseCommand):
    help = "Check that meeting dialect files work as expected. Run this after changes to the files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--exc",
            help="Raise exceptions instead of printing them",
            default=False,
            action="store_true",
        )

    def handle(self, *args, **options):
        raise_exc = options["exc"]
        try:
            dialects_dir = getattr(settings, "MEETING_DIALECTS_DIR", None)
            if dialects_dir is None:
                raise ImproperlyConfigured("MEETING_DIALECTS_DIR missing from settings")
            results = check_dialect_files()
        except Exception as exc:
            if raise_exc:
                raise exc
            sys.exit(str(exc))
        print("Everything worked as expected. Available dialects:")
        for (name, title) in results:
            print(f"{name.ljust(30)} {title}")
