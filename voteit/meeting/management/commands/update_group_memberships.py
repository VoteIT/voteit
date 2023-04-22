from __future__ import annotations

import os
import sys
from collections import defaultdict
from collections.abc import Generator
from logging import getLogger
from typing import TYPE_CHECKING

from django.core.management import BaseCommand
from django.db import transaction

from voteit.meeting.models import GroupMembership
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    pass
logger = getLogger(__name__)


class Command(BaseCommand):
    help = "Create meeting invites. Either piped data or from file."

    def get_data(self, options: dict) -> Generator[list[str]]:
        filename = options.get("f")
        if filename:
            if os.path.isabs(filename):
                filepath = filename
            else:
                cwd = os.getcwd()
                filepath = os.path.join(cwd, filename)
            logger.debug("Loading data from file: %" % filepath)
            with open(filepath, "r") as f:
                data = f.readlines()
        else:
            data = sys.stdin.readlines()
        if not data:
            raise SystemExit("No data to work with")
        for row in data:
            yield [x.strip() for x in row.split("\t")]

    def add_arguments(self, parser):
        parser.add_argument("-m", help="Meeting pk", required=True)
        # parser.add_argument("--cols", help="Columns, comma separated. Defaults to ")
        parser.add_argument(
            "--dry-run",
            help="Don't save anything, just report",
            action="store_true",
            default=False,
        )
        parser.add_argument("-f", help="From file instead of stdin")

    def handle(self, *args, **options):
        meeting: Meeting = Meeting.objects.get(pk=options.get("m"))
        logger.debug("Updating meeting %s with pk %s", meeting.title, meeting.pk)
        # columns = ["email", "groupid", "roleid"]
        email_key_formatted = defaultdict(list)
        groupids = set()
        roleids = set()
        skipped = 0
        not_found_users = 0
        memberships_created = 0
        roles_added = 0
        roles_changed = 0
        roles_cleared = 0
        for i, row in enumerate(self.get_data(options)):
            if not row:
                continue
            row_len = len(row)
            if row_len not in (2, 3):
                raise ValueError(f"Row {i} has {row_len} columns, it must have 2 or 3")
            email = row.pop(0)
            if not email:
                skipped += 1
                continue
            groupid = row.pop(0)
            roleid = row.pop(0) if row else None
            email_key_formatted[email].append({"groupid": groupid, "roleid": roleid})
            groupids.add(groupid)
            if roleid:
                roleids.add(roleid)
        # Check groups
        group_qs = meeting.groups.filter(groupid__in=groupids)
        missing = groupids - set(group_qs.values_list("groupid", flat=True))
        if missing:
            raise ValueError(f"The following groupids missing: {missing}")
        groupid_to_pk = {x.groupid: x.pk for x in group_qs}
        # Check roles
        role_qs = meeting.group_roles.filter(role_id__in=roleids)
        missing = roleids - set(role_qs.values_list("role_id", flat=True))
        if missing:
            raise ValueError(f"The following role_ids missing: {missing}")
        role_id_to_pk = {x.role_id: x.pk for x in role_qs}
        # Participants
        participants_qs = meeting.participants.filter(email__in=email_key_formatted)
        email_to_user_pk = {x.email: x.pk for x in participants_qs}
        print(
            f"Found {len(email_to_user_pk)} matching users of "
            f"requested {len(email_key_formatted)} emails"
        )
        with transaction.atomic(durable=True):
            for email, groupdatas in email_key_formatted.items():
                user_pk = email_to_user_pk.get(email)
                if not user_pk:
                    not_found_users += 1
                    continue
                for groupdata in groupdatas:
                    meeting_group_pk = groupid_to_pk[groupdata["groupid"]]
                    role_pk = (
                        role_id_to_pk[groupdata["roleid"]]
                        if groupdata["roleid"]
                        else None
                    )
                    membership = GroupMembership.objects.filter(
                        user_id=user_pk, meeting_group_id=meeting_group_pk
                    ).first()
                    if membership is None:
                        # Create, will also signal for role so no problem
                        GroupMembership.objects.create(
                            user_id=user_pk,
                            meeting_group_id=meeting_group_pk,
                            role_id=role_pk,
                        )
                        memberships_created += 1
                    else:
                        if membership.role_id and not role_pk:
                            # Role removed
                            old_role = membership.role
                            membership.role = None
                            membership.save()
                            membership.signal_role_removed(role=old_role)
                            roles_cleared += 1
                        elif not membership.role_id and role_pk:
                            # Role added
                            membership.role_id = role_pk
                            membership.save()
                            membership.signal_role_added()
                            roles_added += 1
                        elif (
                            membership.role_id
                            and role_pk
                            and membership.role_id != role_pk
                        ):
                            # Changed
                            old_role = membership.role
                            membership.role = None
                            membership.save()
                            membership.signal_role_removed(role=old_role)
                            membership.role_id = role_pk
                            membership.save()
                            membership.signal_role_added()
                            roles_changed += 1
            processed_count = len(email_key_formatted)
            print(f"Processed {processed_count} emails")
            print(
                f"Users found: {processed_count - not_found_users}   -- missing: {not_found_users} (in meeting)"
            )
            if memberships_created:
                print(
                    f"Memberships (and possibly roles) created: {memberships_created}"
                )
            if roles_added:
                print(f"Roles added to existing memberships: {roles_added}")
            if roles_changed:
                print(f"Roles changed in existing memberships: {roles_changed}")
            if roles_cleared:
                print(f"Roles removed from existing memberships: {roles_cleared}")
            if options.get("dry_run"):
                logger.info("-- DRY RUN - aborting save")
                transaction.set_rollback(True)
