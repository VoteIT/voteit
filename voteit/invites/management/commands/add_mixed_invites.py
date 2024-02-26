from __future__ import annotations


from voteit.invites.management.base import BaseInvitesCommand
from voteit.invites.messages import AddInvites
from voteit.invites.schemas import schema_context
from voteit.meeting.models import Meeting


class Command(BaseInvitesCommand):
    help = "Create meeting invites with different user data types. Either piped data or from file."

    def add_arguments(self, parser):
        self.add_base_arguments(parser)
        self.add_role_arguments(parser)
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
        with schema_context(limit=None):
            command = AddInvites(
                mm={"user_pk": options.get("u")},
                meeting=meeting.pk,
                roles=roles,
                rows=rows,
                columns=cols,
                dryrun=options.get("dry_run"),
            )
            command.context = meeting
            self.run_cmd(command, options)
