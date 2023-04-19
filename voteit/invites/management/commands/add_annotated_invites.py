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
from voteit.invites.messages import AddAnnotatedInvites
from voteit.invites.messages import AddInvites
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER


if TYPE_CHECKING:
    ...
    # from voteit.core.models import User as UserType


_ROLES = {
    "P": str(ROLE_PROPOSER),
    "D": str(ROLE_DISCUSSER),
    "V": str(ROLE_POTENTIAL_VOTER),
}


class Command(BaseCommand):
    help = "Create meeting invites. Note! This command only works with piped data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cols",
            help="Columns, comma separated. Must be specified unless first line is cols",
        )
        parser.add_argument("-m", help="Meeting pk", required=True)
        parser.add_argument("-u", help="Creating user pk", required=True)
        parser.add_argument("-t", help="Invite type", default="email")
        parser.add_argument(
            "--dry-run",
            help="Don't save anything, just report",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--queries",
            help="Report exec time, queries etc",
            action="store_true",
            default=False,
        )
        parser.add_argument("-f", help="From file instead of stdin")
        parser.add_argument(
            "-P", help="Add proposer role", action="store_true", default=False
        )
        parser.add_argument(
            "-D", help="Add discusser role", action="store_true", default=False
        )
        parser.add_argument(
            "-V", help="Add potential voter role", action="store_true", default=False
        )

    def handle(self, *args, **options):
        meeting: Meeting = Meeting.objects.get(pk=options.get("m"))
        roles = {str(ROLE_PARTICIPANT)}
        for (k, role) in _ROLES.items():
            if options.get(k):
                roles.add(role)
        print(
            "Adding invites with roles: {roles} to meeting {meeting}".format(
                roles=", ".join(roles), meeting=meeting.title
            )
        )
        print(
            "Note! This command will freeze if you haven't piped any data to STDIN or specified a file. Exit in that case."
        )
        filename = options.get("f")
        if filename:
            if os.path.isabs(filename):
                filepath = filename
            else:
                cwd = os.getcwd()
                filepath = os.path.join(cwd, filename)
            with open(filepath, "r") as f:
                rows = f.readlines()
        else:
            rows = sys.stdin.readlines()
        if not rows:
            raise SystemExit("No rows")
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
        with transaction.atomic(durable=True):
            conn = get_connection()
            with CaptureQueriesContext(connection=conn) as cqc:
                with exectime() as et:
                    result = command.run_job()
                if options.get("queries"):
                    # pprint(cqc.captured_queries)
                    print("-" * 80)
                    print(f"Execution time: {et():.4f} secs - queries: {len(cqc)}")
            if options.get("dry_run"):
                print("-- DRY RUN - aborting save")
                transaction.set_rollback(True)
        print(
            f"Added: {result.data.added} \nChanged: {result.data.changed} \nExisted: {result.data.existed}"
        )
