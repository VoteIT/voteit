from json import loads

from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core.testing import FakeCommit

User = get_user_model()


class OnCommitLoggerTests(TestCase):
    @property
    def _cut(self):
        from voteit.core.loggers import getOnCommitLogger

        return getOnCommitLogger

    def test_log_on_commit(self):
        with self.assertLogs("hello_world") as logs:
            # assertLogs checks for Logger class so adapters won't work, reinitialize
            logger = self._cut("hello_world")
            with FakeCommit():
                logger.info("Hello")
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))


class LogRolesChangeTests(TestCase):

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from pythonjsonlogger import jsonlogger

        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.meeting = Meeting.objects.get(pk=1)

        cls.json_formatter = jsonlogger.JsonFormatter()

    @property
    def _fut(self):
        from voteit.core.loggers import log_roles_change

        return log_roles_change

    def _mk_dict(self, record):
        # Also to test jsonlogger
        output = self.json_formatter.format(record)
        return loads(output)

    def test_roles_log(self):
        from voteit.meeting.roles import ROLE_MODERATOR

        with self.assertLogs("voteit.event.roles") as logs:
            with FakeCommit():
                self._fut(
                    "Stuff I did",
                    actor=self.moderator,
                    for_user=self.participant,
                    context=self.meeting,
                    roles=[ROLE_MODERATOR],
                )
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        data = self._mk_dict(logs.records[0])
        self.assertEqual(
            {
                "actor": 1,
                "context_name": "meeting",
                "context_pk": 1,
                "for_user": 2,
                "message": "Stuff I did",
                "roles": ["moderator"],
            },
            data,
        )
