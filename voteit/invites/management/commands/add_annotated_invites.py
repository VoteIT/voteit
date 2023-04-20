from __future__ import annotations

import os
import sys
from pprint import pprint
from typing import TYPE_CHECKING

from django.core.management import BaseCommand
from django.db import transaction
from django.db.transaction import get_connection
from django.test.utils import CaptureQueriesContext

from voteit.core.testing import exectime
from voteit.invites.management.commands.base import BaseInvitesCommandMixin
from voteit.invites.messages import AddAnnotatedInvites
from voteit.meeting.models import Meeting


if TYPE_CHECKING:
    ...
    # from voteit.core.models import User as UserType


class Command(BaseCommand, BaseInvitesCommandMixin):
    help = "Create meeting invites with annotations. Either piped data or from file."

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
        command = AddAnnotatedInvites(
            mm={"user_pk": options.get("u")},
            meeting=meeting.pk,
            roles=roles,
            rows=rows,
            columns=cols,
        )
        command.context = meeting
        self.run_cmd(command, options)
