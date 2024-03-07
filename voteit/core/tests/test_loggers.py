from json import loads

from django.contrib.auth import get_user_model
from django.test import TestCase
from pythonjsonlogger.jsonlogger import JsonFormatter

from rest_framework.test import APIRequestFactory

from voteit.core.testing import FakeCommit

User = get_user_model()

json_formatter = JsonFormatter()


def _record_to_dict(record):
    # Also to test jsonlogger
    output = json_formatter.format(record)
    return loads(output)


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


class EventLoggerTests(TestCase):
    @property
    def _cut(self):
        from voteit.core.loggers import getEventLogger

        return getEventLogger

    def test_log_request(self):
        user = User.objects.create(username="actor")
        self.client.force_login(user)

        # Using the standard RequestFactory API to create a form POST request
        factory = APIRequestFactory()
        request = factory.post("/notes/", {"title": "new idea"})

        with self.assertLogs("hello_world") as logs:
            # assertLogs checks for Logger class so adapters won't work, reinitialize
            logger = self._cut("hello_world")
            with FakeCommit():
                logger.info("Wave", request=request)
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        data = _record_to_dict(logs.records[0])
        data.pop("taskName", None)  # Not important here
        self.assertEqual(
            {"message": "Wave", "actor": None, "path": "/notes/", "method": "POST"},
            data,
        )


class LogRolesChangeTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.meeting = Meeting.objects.get(pk=1)

    @property
    def _fut(self):
        from voteit.core.loggers import log_roles_change

        return log_roles_change

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
        data = _record_to_dict(logs.records[0])
        data.pop("taskName", None)  # Not important here
        self.assertEqual(
            {
                "actor": 1,
                "context_name": "meeting",
                "context": 1,
                "for_user": 2,
                "message": "Stuff I did",
                "roles": [ROLE_MODERATOR],
                "meeting": 1,
                "org": 1,
            },
            data,
        )
