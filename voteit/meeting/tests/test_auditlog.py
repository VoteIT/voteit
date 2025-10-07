from auditlog.context import set_actor
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import Organisation
from voteit.poll.app.er_policies.auto_always import AutoAlways

User = get_user_model()


class AuditlogIntegrationTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.org_manager = User.objects.get(username="org_manager")

    def test_create(self):
        with set_actor(self.org_manager):
            meeting: Meeting = self.org.meetings.create(
                title="Hello",
                installed_dialect="bonkers",
                er_policy_name=AutoAlways.name,
                proposal_id_policy_name="404",
            )
        entry = LogEntry.objects.get_for_object(meeting).last()
        self.maxDiff = None
        self.assertEqual(
            {
                "title": ["None", "Hello"],
                "body": ["None", ""],
                "er_policy_name": ["None", AutoAlways.name],
                "group_roles_active": ["None", "False"],
                "group_votes_active": ["None", "False"],
                "installed_dialect": ["None", "bonkers"],
                "organisation": ["None", "1"],
                "proposal_id_policy_name": ["None", "404"],
                "public": ["None", "False"],
                "state": ["None", "upcoming"],
                "visible_in_lists": ["None", "False"],
            },
            entry.changes_dict,
        )

    def test_create_roles(self):
        with set_actor(self.org_manager):
            meeting: Meeting = self.org.meetings.create(title="Hello")
            meeting.add_roles(self.org_manager, ROLE_PARTICIPANT)
        entry = LogEntry.objects.all().first()
        self.assertEqual(("meeting", "meetingroles"), entry.content_type.natural_key())
        # This is not what we want
        self.assertEqual(
            {"assigned": ["[]", "{Participant (pa)}"]},
            entry.changes_dict,
        )
