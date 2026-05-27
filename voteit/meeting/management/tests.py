from io import StringIO

from django.test import override_settings
from django.test import TestCase
from django.core.management import call_command
from pydantic import ValidationError

from voteit.meeting.tests.fixtures import BROKEN_DIALECT_FIXTURE
from voteit.meeting.tests.fixtures import BAD_VALUE_DIALECT_FIXTURE
from voteit.meeting.tests.fixtures import DIALECT_FIXTURES


class CommandsTests(TestCase):
    def call_command(self, cmd, *args, **kwargs):
        out = StringIO()
        call_command(
            cmd,
            *args,
            stdout=out,
            **kwargs,
        )
        return out.getvalue()

    @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
    def test_meeting_dialect_files(self):
        self.call_command("check_meeting_dialect_files")

    @override_settings(MEETING_DIALECTS_DIR=BAD_VALUE_DIALECT_FIXTURE)
    def test_meeting_dialect_files_bad(self):
        with self.assertRaises(SystemExit):
            self.call_command("check_meeting_dialect_files")

    @override_settings(MEETING_DIALECTS_DIR=BAD_VALUE_DIALECT_FIXTURE)
    def test_meeting_dialect_files_bad_w_exec(self):
        with self.assertRaises(ValidationError):
            self.call_command("check_meeting_dialect_files", exc=True)

    @override_settings(MEETING_DIALECTS_DIR=BROKEN_DIALECT_FIXTURE)
    def test_meeting_dialect_files_broken(self):
        with self.assertRaises(TypeError):
            self.call_command("check_meeting_dialect_files", exc=True)
