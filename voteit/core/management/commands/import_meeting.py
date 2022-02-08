from __future__ import annotations

import sys
import os

# from os.path import isfile
from django.db import DEFAULT_DB_ALIAS
from django.db import DatabaseError
from django.db import IntegrityError
from django.db import router
from django.core import serializers
from django.core.management import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from voteit.core.exporters.meeting import MeetingExporters
from voteit.core.importers.meeting import MeetingImporter
from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_shortname
from voteit.meeting.models import Meeting


class Command(BaseCommand):
    help = "Import and create a new meeting. Won't overwrite existing meetings and can be run multiple times."
    # using: str
    # models: set
    # exporters: MeetingExporters
    # meeting_obj: Meeting
    # old_meeting_pk: int
    # agenda_items: dict
    # meeting_groups: dict
    # objs_with_deferred_fields: list

    def add_arguments(self, parser):
        parser.add_argument(
            "filename", help="Output filename, defaults to sluggified meeting title"
        )
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help='Nominates a specific database to load fixtures into. Defaults to the "default" database.',
        )

    def handle(self, *args, **options):
        importer = MeetingImporter(
            using=options["database"], filename=options["filename"]
        )
        try:
            importer.run()
        except ValueError as exc:
            sys.exit(str(exc))
