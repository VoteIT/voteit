from auditlog.context import set_actor
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from ...meeting.models import Meeting
from ..models import HistoryLog

User = get_user_model()


class PopulateJobTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.outsider = User.objects.create(username="outsider")
        cls.participant = User.objects.get(username="participant")

    @staticmethod
    def _do_job() -> HistoryLog:
        from ..jobs import populate_history_log

        populate_history_log(timezone.now())
        return HistoryLog.objects.get()

    def test_populate(self):
        entry = self._do_job()

        self.assertEqual(HistoryLog.objects.all().count(), 1)
        with self.assertRaises(IntegrityError):
            self._do_job()

    def test_connections(self):
        from envelope.models import Connection

        Connection.objects.create(user=self.moderator, last_action=timezone.now())
        Connection.objects.create(user=self.participant, last_action=timezone.now())
        Connection.objects.create(
            channel_name="other", user=self.moderator, last_action=timezone.now()
        )
        entry = self._do_job()

        self.assertEqual(entry.connection_count, 3)
        self.assertEqual(entry.user_online_count, 2)

    def test_action_count(self):
        # TODO: Check with another org, so we know that org filtering works
        meeting = Meeting.objects.get()
        with set_actor(self.moderator):
            ai = meeting.agenda_items.create(title="An agenda item")
            ai.body = "<p>Some content</p>"
            ai.save()
        with set_actor(self.outsider):
            ai.body = "<p>Changed content</p>"
            ai.save()
        entry = self._do_job()
        self.assertEqual(entry.action_count, 2)
