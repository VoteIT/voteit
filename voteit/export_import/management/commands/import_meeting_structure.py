from django.db import transaction

from voteit.export_import.management.base_cmds import BaseExpImpCommand
from voteit.meeting.models import Meeting
from voteit.export_import.importer import Importer
from voteit.export_import.importer import MissingUser


class Command(BaseExpImpCommand):
    help = "Import meeting structure"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("filename", help="Filename")
        parser.add_argument(
            "--commit", help="Commit result to db", action="store_true", default=False
        )
        parser.add_argument(
            "--missing",
            help="Missing user strategy",
            choices=[MissingUser.BLANK, MissingUser.CREATE, MissingUser.RAISE],
            default=MissingUser.RAISE,
        )
        parser.add_argument(
            "--no-part",
            help="Don't add users as participants",
            default=False,
            action="store_true",
        )
        parser.add_argument(
            "--skip-verify",
            help="Skip signature verification",
            default=False,
            action="store_true",
        )

    def handle(self, *args, **options):
        meeting: Meeting = Meeting.objects.get(pk=options.get("m"))
        commit = options.get("commit")
        importer = Importer(
            meeting,
            missing_user=options["missing"],
            include_discussions=not options["skip_disc"],
            include_proposals=not options["skip_prop"],
            add_participants=not options["no_part"],
            clear_group_authors=options["clear_group_authors"],
            clear_authors=options["clear_authors"],
            clear_ai_states=options["clear_ai_states"],
            clear_proposal_states=options["clear_proposal_states"],
            clear_proposal_id=options["clear_proposal_ids"],
            verify=not options["skip_verify"],
        )
        with transaction.atomic(durable=True):
            self.stdout.write(f'Reading and importing {options["filename"]} ...')
            importer.from_file(options["filename"])
            importer.run()
            self.stdout.write(
                f"Imported {len(importer.data.agenda_items)} agenda items, their contained data and {len(importer.data.groups)} groups"
            )
            if commit:
                self.stdout.write(self.style.SUCCESS("Saving..."))
            else:
                self.stdout.write(
                    self.style.WARNING("Aborting transaction - nothing saved")
                )
                transaction.set_rollback(True)
