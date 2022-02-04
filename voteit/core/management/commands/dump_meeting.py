from __future__ import annotations

import sys
from os.path import isfile

from django.core import serializers
from django.core.management import BaseCommand
from django.utils.text import slugify
from voteit.core.exporters.meeting import MeetingExporters
from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_shortname
from voteit.meeting.models import Meeting


class Command(BaseCommand):
    help = "Dump meeting"

    def add_arguments(self, parser):
        parser.add_argument("-m", help="Meeting primary key")
        parser.add_argument(
            "-o", help="Output filename, defaults to sluggified meeting title"
        )
        parser.add_argument(
            "-F",
            help="Force overwrite output file",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--list-exported-models",
            help="Only list exported models, do nothing",
            action="store_true",
            default=False,
        )

    def handle(self, *args, **options):
        if options.get("list_exported_models"):
            exported_shortnames = sorted(
                [
                    get_model_shortname(x)
                    for x in MeetingExporters.get_exportable_models()
                ]
            )
            not_exported_shortnames = sorted(
                set(get_content_registry().keys()) - set(exported_shortnames)
            )
            print("\n### EXPORTED ###")
            [print(x) for x in exported_shortnames]
            print("\n### NOT INCLUDED ###")
            [print(x) for x in not_exported_shortnames]
            sys.exit()
        meeting_pk = pk = options.get("m")
        try:
            meeting: Meeting = Meeting.objects.get(pk=meeting_pk)
        except Meeting.DoesNotExist:
            sys.exit(f"No meeting with pk {meeting_pk}")
        filename = options.get("o")
        if not filename:
            filename = slugify(meeting.title)[:25] + ".yaml"
        meeting_exporters = MeetingExporters(meeting.pk)
        object_count = meeting_exporters.get_object_count()
        if isfile(filename):
            if options.get("F"):
                print(f"Overwriting {filename}")
            else:
                raise sys.exit(f"{filename} already exists, won't overwrite!")
        else:
            print(f"Creating {filename}")
        with open(filename, "w") as stream:
            done = 0
            for exp in meeting_exporters:
                if exp:
                    serializers.serialize(
                        "yaml",
                        exp(),
                        fields=exp.select_fields,
                        # indent=indent,
                        # use_natural_foreign_keys=use_natural_foreign_keys,
                        # use_natural_primary_keys=use_natural_primary_keys,
                        stream=stream,
                        # progress_output=self.stdout,
                        # object_count=object_count,
                    )
                    # Progress bar doesn't work properly
                    done += len(exp)
                    print(f"[{done} / {object_count}]")
