from __future__ import annotations

import sys

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import BaseCommand

from voteit.meeting.utils import check_dialect_files


class Command(BaseCommand):
    help = "Check that meeting dialect files work as expected. Run this after changes to the files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--suppress",
            help="Print exceptions instead of raising them",
            default=False,
            action="store_true",
        )

    def handle(self, *args, **options):
        suppress_exc = options["suppress"]
        try:
            dialects_dir = getattr(settings, "MEETING_DIALECTS_DIR", None)
            if dialects_dir is None:
                raise ImproperlyConfigured("MEETING_DIALECTS_DIR missing from settings")
            check_dialect_files()
        except Exception as exc:
            if suppress_exc:
                sys.exit(str(exc))
            raise exc
