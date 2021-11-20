from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from django.core.management import BaseCommand
from django.db import transaction
from voteit.meeting.models import Meeting
from voteit.participant_number.models import PNSystem

if TYPE_CHECKING:
    from voteit.participant_number.models import ParticipantNumber


class Command(BaseCommand):
    help = "Import participant numbers."

    def add_arguments(self, parser):
        parser.add_argument("-m", help="Meeting pk")
        parser.add_argument(
            "--clear",
            help="Clear existing",
            action="store_true",
            default=False,
        )

    def handle(self, *args, **options):
        meeting: Meeting = Meeting.objects.get(pk=options.get("m"))
        try:
            pn_system = meeting.pn_system
        except PNSystem.DoesNotExist:
            pn_system = PNSystem.objects.create(meeting=meeting)
        print(f"Adding participant numbers to meeting {meeting.title}")
        print(
            "Note! This command will freeze if you haven't piped any data to STDIN. Exit in case you didn't.\n\n"
            "Input must be formatted per row with <number><any space like char><email>.\n"
            "Example:\n"
            "11 john@betahaus.net\n"
        )
        print("-" * 80)
        email_to_pn = {}
        i = 1
        for row in sys.stdin:
            row = row.split()
            if len(row) == 2:
                pn = int(row[0])
                email = row[1].strip().lower()
                if pn in email_to_pn.values():
                    raise SystemExit(f"Error: Row {i} contains duplicate PN: {pn}")
                if email in email_to_pn:
                    raise SystemExit(
                        f"Error: Row {i} contains duplicate email: {email}"
                    )
                email_to_pn[email] = pn
            i += 1
        users_qs = meeting.participants.filter(email__in=list(email_to_pn.keys()))
        found = users_qs.count()
        existed = 0
        with transaction.atomic():
            if options.get("clear"):
                pn_system.numbers.all().delete()
            for user in users_qs:
                pn_obj, _ = pn_system.numbers.get_or_create(
                    user=user, defaults={"number": email_to_pn[user.email]}
                )
                pn_obj: ParticipantNumber
                if pn_obj.number != email_to_pn[user.email]:
                    pn_obj.number = email_to_pn[user.email]
                    pn_obj.save()
                    existed += 1
        print(f"Found {found} participant(s)")
        if existed:
            print(f"Changed number for {existed}")
        missed = len(email_to_pn) - found
        if missed:
            print(f"{missed} participant(s) could not be found.")
