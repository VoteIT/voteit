from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.management import BaseCommand

from voteit.invites.management.commands.base import BaseInvitesCommandMixin
from voteit.invites.messages import AddInviteAnnotations
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    ...
    # from voteit.core.models import User as UserType


class Command(BaseCommand, BaseInvitesCommandMixin):
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
        self.report(
            "Adding invites with roles: {roles} to meeting {meeting}",
            roles=", ".join(roles),
            meeting=meeting.title,
        )
        self.report(
            "Note! This command will freeze if you haven't piped any data to STDIN or specified a file. Exit in that case."
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
                self.report(
                    f"Annotation {result.name}\n"
                    f"Added: {result.data.added} \nChanged: {result.data.changed} \nExisted: {result.data.existed}"
                )
