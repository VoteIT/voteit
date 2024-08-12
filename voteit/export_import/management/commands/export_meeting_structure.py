import yaml
from django.core.management import BaseCommand
from django.db.transaction import get_connection

from voteit.core.testing import exectime
from voteit.meeting.models import Meeting
from voteit.export_import.exporter import Exporter
from django.test.utils import CaptureQueriesContext


class Command(BaseCommand):
    help = "Export meeting structure"

    def add_arguments(self, parser):
        parser.add_argument("-o", help="Output filename")
        parser.add_argument("-m", help="Meeting pk", required=True)
        parser.add_argument(
            "--skip-disc", help="Skip discussions", default=False, action="store_true"
        )
        parser.add_argument(
            "--skip-prop", help="Skip proposals", default=False, action="store_true"
        )
        parser.add_argument(
            "--sql", help="Print sql", default=False, action="store_true"
        )
        parser.add_argument(
            "--sql-limit", help="SQL output limit", default=20, type=int
        )

    def handle(self, *args, **options):
        meeting: Meeting = Meeting.objects.get(pk=options.get("m"))
        exporter = Exporter(
            meeting,
            include_discussions=not options["skip_disc"],
            include_proposals=not options["skip_prop"],
        )

        conn = get_connection()
        with CaptureQueriesContext(connection=conn) as cqc:
            with exectime() as et:
                exporter()
            self.stdout.write(
                f"Execution time: {et():.4f} secs - Queries: {len(cqc)} - "
            )
            if options["sql"]:
                sql_limit = options["sql_limit"]
                self.stdout.write(str(cqc.captured_queries[:sql_limit]))
                if len(cqc.captured_queries) > sql_limit:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Note, there were {len(cqc.captured_queries)} queries but i only wrote {sql_limit}! Sorry :("
                        )
                    )
        if filename := options.get("o"):
            self.stdout.write(f"Writing YAML-file: {filename} ...")
            with open(filename, "w") as f:
                output = exporter.data.dict(exclude_none=True)
                yaml.dump(output, stream=f)
            self.stdout.write(self.style.SUCCESS("Success"))
        else:
            self.stdout.write(
                self.style.WARNING("No output file specified so I'm doing this for fun")
            )
