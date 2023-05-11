from __future__ import annotations


from voteit.invites.management.base import BaseInvitesCommand
from voteit.invites.messages import AddInviteAnnotations
from voteit.meeting.models import Meeting


class Command(BaseInvitesCommand):
    help = "Create meeting invites with different user data types. Either piped data or from file."

    def add_arguments(self, parser):
        self.add_base_arguments(parser)
        parser.add_argument(
            "--cols",
            help="Columns, comma separated. Must be specified unless first line is cols",
        )

    def handle(self, *args, **options):
        self.quiet = options.get("q")
        meeting: Meeting = Meeting.objects.get(pk=options.get("m"))
        roles = self.get_roles(options)
        self.stdout.write(
            "Adding invites with roles: {roles} to meeting {meeting}".format(
                roles=", ".join(roles),
                meeting=meeting.title,
            )
        )
        rows = self.get_data(options)
        cols = options.get("cols")
        if cols:
            cols = cols.split(",")
        else:
            cols = rows.pop(0).split("\t")
        command = AddInviteAnnotations(
            mm={"user_pk": options.get("u")},
            meeting=meeting.pk,
            rows=rows,
            columns=cols,
            dryrun=options.get("dry_run"),
        )
        command.context = meeting
        for result in self.run_cmd(command, options):
            if result:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Annotation {result.name}\n"
                        f"Added: {result.data.added} \nChanged: {result.data.changed} \nExisted: {result.data.existed}"
                    )
                )
