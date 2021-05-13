from pprint import pprint

import yaml
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = "List registered transitions."

    def handle(self, *args, **options):
        from voteit.core.utils import get_available_transitions

        for (k, v) in get_available_transitions().items():
            print("-" * 10, " ", k)
            for item in v:
                print(item)
