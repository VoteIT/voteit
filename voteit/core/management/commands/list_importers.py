from __future__ import annotations

import sys
from itertools import chain
from os.path import isfile

from django.core import serializers
from django.core.management import BaseCommand
from django.utils.text import slugify
from voteit.core.exporters.meeting import MeetingExporters
from voteit.core.importers.organisation import OrganisationImport
from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_shortname
from voteit.meeting.models import Meeting


class Command(BaseCommand):
    help = "Export meeting"

    def add_arguments(self, parser):
        parser.add_argument("--name", help="List models handled by this importer")

    def handle(self, *args, **options):
        reg = get_content_registry()
        importer_name = options.get("name")
        if importer_name:
            handled_by_importer = set()
            not_handled = set()
            not_remapped_relations = {}
            for shortname, model in reg.items():
                if importers := getattr(model, "importers", None):
                    if importer_name in importers:
                        handled_by_importer.add(shortname)
                        # FIXME: Assume settings with importer name for now
                        try:
                            org_import = OrganisationImport(**importers[importer_name])
                        except Exception as exc:
                            print(
                                f"Model: {model} - Importers settings: {importers[settings_key]}"
                            )
                            raise
                        # Check fields
                        remapped = set(
                            chain(*[v for v in org_import.remap_relations.values()])
                        )
                        for field in model._meta.local_concrete_fields:
                            if not field.is_relation:
                                continue
                            if field.name not in remapped:
                                items = not_remapped_relations.setdefault(
                                    shortname, set()
                                )
                                items.add(field.name)
                    else:
                        not_handled.add(shortname)
            if not handled_by_importer:
                sys.exit(
                    f"=== There are no models handled by importer *{importer_name}*"
                )
            print(
                f"=== The following models are handled by importer *{importer_name}* ==="
            )
            print("=" * 80)
            for name in sorted(handled_by_importer):
                print(name)
                if name in not_remapped_relations:
                    print("-- Unhandled relation attrs:")
                    for v in not_remapped_relations[name]:
                        print(f"  -- {v}")
            print("=== Not handled: ===")
            for name in sorted(not_handled):
                print(name)
        else:
            found = set()
            for model in reg.values():
                found.update(getattr(model, "importers", []))
            print("=== The following importers exist on content types: ===")
            for name in sorted(found):
                print(name)
