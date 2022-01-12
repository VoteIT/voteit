from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand
from django.db import transaction

from voteit.invites.utils import create_invites
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER

User = get_user_model()

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


_ROLES = {
    "P": str(ROLE_PROPOSER),
    "D": str(ROLE_DISCUSSER),
    "V": str(ROLE_POTENTIAL_VOTER),
}


class Command(BaseCommand):
    help = "Create meeting invites. Note! This command only works with piped data."

    def add_arguments(self, parser):
        parser.add_argument("-m", help="Meeting pk")
        parser.add_argument("-u", help="Creating user pk")
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
        created_by: UserType = User.objects.get(pk=options.get("u"))
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
            "Note! This command will freeze if you haven't piped any data to STDIN. Exit in case you didn't."
        )
        emails = set()
        for row in sys.stdin:
            row = row.strip()
            if row:
                emails.add(row)
        with transaction.atomic():
            added, changed, skipped_count = create_invites(
                created_by=created_by,
                meeting=meeting.pk,
                roles=roles,
                invite_data=emails,
            )
        print(
            f"Added: {len(added)} \nChanged: {len(changed)} \nSkipped: {skipped_count}"
        )
