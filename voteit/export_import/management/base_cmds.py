from django.core.management import BaseCommand


class BaseExpImpCommand(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("-m", help="Meeting pk", required=True)
        parser.add_argument(
            "--skip-disc", help="Skip discussions", default=False, action="store_true"
        )
        parser.add_argument(
            "--skip-prop", help="Skip proposals", default=False, action="store_true"
        )
        parser.add_argument(
            "--clear-group-authors",
            help="Clear group authors",
            default=False,
            action="store_true",
        )
        parser.add_argument(
            "--clear-authors",
            help="Clear authors",
            default=False,
            action="store_true",
        )
        parser.add_argument(
            "--clear-ai-states",
            help="Clear agenda item states",
            default=False,
            action="store_true",
        )
        parser.add_argument(
            "--clear-proposal-states",
            help="Clear proposal states",
            default=False,
            action="store_true",
        )
        parser.add_argument(
            "--clear-proposal-ids",
            help="Clear proposal ids",
            default=False,
            action="store_true",
        )
