from auditlog.context import set_actor
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import Meeting

User = get_user_model()


class AuditlogIntegrationTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()

    def test_create(self):
        with set_actor(self.moderator):
            poll = self.ai.polls.create(method_name="simple")
        entry = LogEntry.objects.get_for_object(poll).last()
        self.assertEqual(
            {
                "meeting": ["None", f"{self.meeting.pk}"],
                "agenda_item": ["None", f"{self.ai.pk}"],
                "method_name": ["None", "simple"],
                "p_ord": ["None", "c"],
                "state": ["None", "private"],
                "title": ["None", " 1"],
                "withheld_result": ["None", "False"],
            },
            entry.changes_dict,
        )
