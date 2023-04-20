import os
import sys
from logging import getLogger
from pprint import pprint

from django.db import transaction
from django.db.transaction import get_connection
from django.test.utils import CaptureQueriesContext

from voteit.core.testing import exectime
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


class BaseInvitesCommandMixin:
    quiet = False

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
        parser.add_argument("-q", help="Quiet")
        parser.add_argument(
            "-P", help="Add proposer role", action="store_true", default=False
        )
        parser.add_argument(
            "-D", help="Add discusser role", action="store_true", default=False
        )
        parser.add_argument(
            "-V", help="Add potential voter role", action="store_true", default=False
        )

    def report(self, txt, lvl="debug", **kwargs):
        if not self.quiet:
            method = getattr(logger, lvl)
            method(txt.format(**kwargs))

    def get_roles(self, options: dict) -> set[str]:
        roles = {str(ROLE_PARTICIPANT)}
        for (k, role) in _ROLES.items():
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
            self.report("Loading data from file: {filepath}", filepath=filepath)
            with open(filepath, "r") as f:
                data = f.readlines()
        else:
            data = sys.stdin.readlines()
        if not data:
            raise SystemExit("No data to work with")
        return data

    def run_cmd(self, cmd, options: dict):
        with transaction.atomic(durable=True):
            conn = get_connection()
            with CaptureQueriesContext(connection=conn) as cqc:
                with exectime() as et:
                    result = cmd.run_job()
                if options.get("queries"):
                    # pprint(cqc.captured_queries)

                    self.report(
                        f"Execution time: {et():.4f} secs - queries: {len(cqc)}"
                    )
            if options.get("dry_run"):
                self.report("-- DRY RUN - aborting save")
                transaction.set_rollback(True)
        self.report(
            f"Added: {result.data.added} \nChanged: {result.data.changed} \nExisted: {result.data.existed}"
        )
