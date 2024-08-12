from django.core.management import BaseCommand
from django.db import transaction

from voteit.meeting.models import Meeting
from voteit.export_import.importer import Importer
from voteit.export_import.importer import MissingUser


class Command(BaseCommand):
    help = "Import meeting structure"

    def add_arguments(self, parser):
        parser.add_argument("filename", help="Filename")
        parser.add_argument("-m", help="Meeting pk", required=True)
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
            "--skip-disc", help="Skip discussions", default=False, action="store_true"
        )
        parser.add_argument(
            "--skip-prop", help="Skip proposals", default=False, action="store_true"
        )
        parser.add_argument(
            "--no-part",
            help="Don't add users as participants",
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
