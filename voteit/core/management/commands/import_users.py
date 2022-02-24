from __future__ import annotations

import json
import sys
from django.core.management import BaseCommand
from django.db import DEFAULT_DB_ALIAS

from voteit.core.importers.user import UserImporter


class Command(BaseCommand):
    help = "Import users that doesn't exist within the database (matched on email). Save a map of pks from import -> db"

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
            help="Organisation pk to add users to",
        )
        parser.add_argument(
            "--outfile",
            help="File to write remapped users to, as json",
        )

    def handle(self, *args, **options):
        assert "org" in options
        importer = UserImporter(using=options["database"], filename=options["filename"])
        import_pk_to_db_pk = importer.run(
            dry=options["dry_run"], existing_organisation_pk=options["org"]
        )
        # print(
        #     "Here are the remapped user_pks - import value as key, db value as value:"
        # )
        if options.get("outfile"):
            if options["dry_run"]:
                sys.exit("Error: Will not write output file - dry run")
            with open(options["outfile"], "w") as outfile:
                json.dump(import_pk_to_db_pk, outfile)
                print(
                    f"Wrote file {options['outfile']} with {len(import_pk_to_db_pk)} entries. "
                    f"Key is import pk and value is db pk"
                )
