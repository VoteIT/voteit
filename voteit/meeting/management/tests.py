from io import StringIO

from django.test import override_settings
from django.test import TestCase
from django.core.management import call_command
from pydantic import ValidationError

from voteit.meeting.tests.fixtures import BAD_DIALECT_FIXTURES
from voteit.meeting.tests.fixtures import DIALECT_FIXTURES


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
            self.call_command("check_meeting_dialect_files", exc=True)
        with self.assertRaises(SystemExit):
            self.call_command("check_meeting_dialect_files")
