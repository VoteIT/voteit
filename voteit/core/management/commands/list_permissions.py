from pprint import pprint

from django.core.management import BaseCommand


class Command(BaseCommand):
    help = "List registered permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "-m", help="Only for a specific model, specify Django-style name "
        )

    def handle(self, *args, **options):
        from voteit.core.registries import permissions
        from rules.permissions import permissions as rules_perms

        only_model = options.get("m")
        if only_model:
            assert (
                "." in only_model
            ), "Specify Django-style model names like meeting.Meeting"
            perms = permissions.for_model(only_model)
        else:
            perms = permissions.values()
        print("-" * 80)
        print("Listing permissions")
        print("=" * 80)
        for perm in perms:
            data = perm.output().dict(skip_defaults=True)
            pred = rules_perms.get(perm)
            if pred is not None:
                data["predicate"] = pred
            pprint(data)
            print("-" * 80)
