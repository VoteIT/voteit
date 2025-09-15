import yaml
from django.db.transaction import get_connection

from voteit.core.utils import exectime
from voteit.export_import.management.base_cmds import BaseExpImpCommand
from voteit.export_import.utils import sign_payload
from voteit.meeting.models import Meeting
from voteit.export_import.exporter import Exporter
from django.test.utils import CaptureQueriesContext


class Command(BaseExpImpCommand):
    help = "Export meeting structure"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("-o", help="Output filename")
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
            include_buttons=not options["skip_btn"],
            clear_group_authors=options["clear_group_authors"],
            clear_authors=options["clear_authors"],
            clear_ai_states=options["clear_ai_states"],
            clear_proposal_states=options["clear_proposal_states"],
            clear_proposal_id=options["clear_proposal_ids"],
            include_reactions=options["include_reactions"],
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
            payload = yaml.dump(exporter.data.dict(exclude_none=True))
            signed_payload = f"sign: {sign_payload(payload)}\n" + payload
            with open(filename, "w") as f:
                f.write(signed_payload)
            self.stdout.write(self.style.SUCCESS("Success"))
        else:
            self.stdout.write(
                self.style.WARNING("No output file specified so I'm doing this for fun")
            )
