import yaml
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = "List registered predicates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            help="Print source of predicate",
            action="store_true",
            default=False,
        )
        # parser.add_argument(
        #     "-m", help="Only for a specific model, specify Django-style name "
        # )

    def handle(self, *args, **options):
        from voteit.core.registries import predicates

        # only_model = options.get("m")
        # if only_model:
        #     assert (
        #         "." in only_model
        #     ), "Specify Django-style model names like meeting.Meeting"
        #     perms = permissions.for_model(only_model)
        # else:
        #     perms = permissions.values()
        print("-" * 80)
        print("Listing predicates")
        print("=" * 80)
        for predicate in predicates.values():
            out = predicate.output()
            print(
                yaml.dump(
                    out.dict(skip_defaults=True, exclude_none=True, exclude={"source"})
                )
            )
            print(out.source)
            print("-" * 80)
