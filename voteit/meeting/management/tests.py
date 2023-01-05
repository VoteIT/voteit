import os
from io import StringIO

from django.test import override_settings
from django.test import TestCase
from django.core.management import call_command
from pydantic import ValidationError

TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests")
DIALECT_FIXTURES = os.path.join(TESTS_DIR, "dialect_fixtures")
BAD_DIALECT_FIXTURES = os.path.join(TESTS_DIR, "bad_dialect_fixtures")


class CommandsTests(TestCase):
    def call_command(self, cmd, *args, **kwargs):
        out = StringIO()
        call_command(
            cmd,
            *args,
            stdout=out,
            # stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
    def test_meeting_dialect_files(self):
        out = self.call_command("check_meeting_dialect_files")

    @override_settings(MEETING_DIALECTS_DIR=BAD_DIALECT_FIXTURES)
    def test_meeting_dialect_files_bad(self):
        with self.assertRaises(ValidationError):
            self.call_command("check_meeting_dialect_files")
        with self.assertRaises(SystemExit):
            self.call_command("check_meeting_dialect_files", suppress=True)
