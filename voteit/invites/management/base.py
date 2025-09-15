import os
import select
import sys
from logging import getLogger

from django.core.management import BaseCommand
from django.core.management import CommandError
from django.db.transaction import get_connection
from django.test.utils import CaptureQueriesContext

from voteit.core.utils import exectime
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER

_ROLES = {
    "P": str(ROLE_PROPOSER),
    "D": str(ROLE_DISCUSSER),
    "V": str(ROLE_POTENTIAL_VOTER),
}

logger = getLogger(__name__)


class BaseInvitesCommand(BaseCommand):
    def add_base_arguments(self, parser):
        parser.add_argument("-m", help="Meeting pk", required=True)
        parser.add_argument("-u", help="Creating user pk", required=True)
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

    def add_role_arguments(self, parser):
        parser.add_argument(
            "-P", help="Add proposer role", action="store_true", default=False
        )
        parser.add_argument(
            "-D", help="Add discusser role", action="store_true", default=False
        )
        parser.add_argument(
            "-V", help="Add potential voter role", action="store_true", default=False
        )

    def get_roles(self, options: dict) -> set[str]:
        roles = {str(ROLE_PARTICIPANT)}
        for k, role in _ROLES.items():
            if options.get(k):
                roles.add(role)
        return roles

    def get_data(self, options: dict):
        filename = options.get("f")
        if filename:
            if os.path.isabs(filename):
                filepath = filename
            else:
                cwd = os.getcwd()
                filepath = os.path.join(cwd, filename)

            self.stdout.write(f"Loading data from file: {filepath}")
            with open(filepath, "r") as f:
                data = f.readlines()
            if not data:
                raise CommandError("Specified file empty")
        else:
            data = None
            if select.select([sys.stdin], [], [], 1.0)[0]:
                data = sys.stdin.readlines()
            if not data:
                raise CommandError("No data received from STDIN")
        return data

    def run_cmd(self, cmd, options: dict):
        conn = get_connection()
        with CaptureQueriesContext(connection=conn) as cqc:
            with exectime() as et:
                result = cmd.run_job()
            if options.get("queries"):
                # pprint(cqc.captured_queries)
                self.stdout.write(
                    f"Execution time: {et():.4f} secs - queries: {len(cqc)}"
                )
        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING("-- DRY RUN - save was aborted"))
        return result
