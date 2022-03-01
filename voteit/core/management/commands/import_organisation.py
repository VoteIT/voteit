from __future__ import annotations

import yaml
from django.core.management import BaseCommand
from django.core.serializers.base import DeserializedObject
from django.db import DEFAULT_DB_ALIAS

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
        parser.add_argument(
            "-o",
            help="Output filemap",
        )

    def handle(self, *args, **options):
        filemap_name = options["o"]
        importer = OrganisationImporter(
            using=options["database"], filename=options["filename"]
        )
        importer.run(dry=options["dry_run"], existing_organisation_pk=options["org"])
        if filemap_name:
            print(f"Writing filemap as {filemap_name}")
            data = {}
            for k, v in importer.objects_to_handle.items():
                data[k] = []
                for obj in v.values():
                    # Only deserialized objects, other instances were loaded from the db
                    if isinstance(obj, DeserializedObject):
                        data[k].append(obj.object.pk)
            with open(filemap_name, "w") as filemap:
                yaml.dump(data, filemap)
