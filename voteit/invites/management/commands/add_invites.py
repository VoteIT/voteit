from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.invites.management.base import BaseInvitesCommand
from voteit.invites.messages import AddInvites
from voteit.invites.schemas import schema_context
from voteit.meeting.models import Meeting


if TYPE_CHECKING:
    pass


class Command(BaseInvitesCommand):
    help = "Create meeting invites. Either piped data or from file."

    def add_arguments(self, parser):
        self.add_base_arguments(parser)
        self.add_role_arguments(parser)
        parser.add_argument("-t", help="Invite type", default="email")

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
        user_data = self.get_data(options)
        cleaned_userdata = sorted(set(user_data))
        if len(user_data) != len(cleaned_userdata):
            self.stdout.write(
                self.style.WARNING(
                    f"Removed {len(user_data) - len(cleaned_userdata)} item(s) from list since they were duplicated"
                )
            )
        with schema_context(limit=None):
            command = AddInvites(
                mm={"user_pk": options.get("u")},
                meeting=meeting.pk,
                roles=roles,
                rows=cleaned_userdata,
                columns=["email"],
                dryrun=options.get("dry_run"),
            )
            command.context = meeting
            response = self.run_cmd(command, options)
        self.stdout.write(
            self.style.SUCCESS(
                f"Added: {response.data.added} Changed: {response.data.changed} Existed: {response.data.existed}"
            )
        )
