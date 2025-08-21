from auditlog.context import set_actor
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.access_policy.app.policies import AutomaticAccess
from voteit.meeting.models import Meeting

User = get_user_model()


class AuditlogIntegrationTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")

    def test_create(self):
        with set_actor(self.moderator):
            ap = AutomaticAccess.objects.create(
                meeting=self.meeting, roles_given=["pa"]
            )
        entry = LogEntry.objects.get_for_object(ap).last()
        self.assertEqual(
            {
                "active": ["None", "False"],
                "meeting": ["None", f"{self.meeting.pk}"],
                "roles_given": ["None", "['pa']"],
            },
            entry.changes_dict,
        )
