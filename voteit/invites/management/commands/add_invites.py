from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.management import BaseCommand
from django.db import transaction

from voteit.invites.management.commands.base import BaseInvitesCommandMixin
from voteit.invites.messages import AddInvites
from voteit.meeting.models import Meeting


if TYPE_CHECKING:
    from voteit.core.models import User as UserType


class Command(BaseCommand, BaseInvitesCommandMixin):
    help = "Create meeting invites. Either piped data or from file."

    def add_arguments(self, parser):
        self.add_base_arguments(parser)
        parser.add_argument("-t", help="Invite type", default="email")

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
        user_data = self.get_data(options)
        command = AddInvites(
            mm={"user_pk": options.get("u")},
            meeting=meeting.pk,
            roles=roles,
            user_data=user_data,
        )
        command.context = meeting
        with transaction.atomic(durable=True):
            result = self.run_cmd(command, options)
        self.report(
            f"Added: {result.data.added} \nChanged: {result.data.changed} \nExisted: {result.data.existed}"
        )
