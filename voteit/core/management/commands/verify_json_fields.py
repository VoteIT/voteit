from __future__ import annotations

import sys

from django.core.management import BaseCommand

from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.speaker.models import SpeakerListSystem


class Command(BaseCommand):
    help = "Verify json fields for: poll, vote, speaker_system"

    def add_arguments(self, parser):
        parser.add_argument("--only", help="Only check this model")
        parser.add_argument(
            "--errors", help="Show errors", default=False, action="store_true"
        )

    def handle(self, *args, **options):
        show_errors = options["errors"]
        only_model = options["only"]
        to_check = [
            [Poll, {"settings", "result"}],
            [Vote, {"vote"}],
            [SpeakerListSystem, {"settings"}],
        ]
        fails = {Poll.name: set(), Vote.name: set(), SpeakerListSystem.name: set()}
        if only_model and only_model not in fails:
            sys.exit(f"Can't check model {only_model}")
        for model, attrs in to_check:
            if only_model and model.name != only_model:
                continue
            all_objs = model.objects.all().order_by("pk")
            print(f"Checking {all_objs.count()} {model.name}(s)")
            for obj in all_objs:
                for attr in attrs:
                    try:
                        getattr(obj, attr)
                    except ValueError as exc:
                        fails[model.name].add(obj.pk)
                        if show_errors:
                            print(f"--- {model.name} attr {attr} pk: {obj.pk} ---")
                            print(exc)
        errors_count = sum([len(x) for x in fails.values()])
        if sum([len(x) for x in fails.values()]):
            sys.exit(f"=== There were {errors_count} errors")
        else:
            print("=== Everything worked!")
