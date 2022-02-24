from __future__ import annotations

import sys

from django.core.management import BaseCommand
from django.db import DEFAULT_DB_ALIAS

from voteit.core.importers.meeting import MeetingImporter
from voteit.core.importers.organisation import OrganisationImporter


class Command(BaseCommand):
    help = (
        "Import all organisation related things. Merge with an existing organisation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "filename",
            help="Input file to read from",
        )
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help='Nominates a specific database to load fixtures into. Defaults to the "default" database.',
        )
        parser.add_argument(
            "--dry-run",
            default=False,
            action="store_true",
            help="Do nothing, just report",
        )
        parser.add_argument(
            "--org",
            help="Organisation pk to append content to",
        )

    def handle(self, *args, **options):
        importer = OrganisationImporter(
            using=options["database"], filename=options["filename"]
        )
        importer.run(dry=options["dry_run"], existing_organisation_pk=options["org"])
        # try:
        # except ValueError as exc:
        #     sys.exit(str(exc))
