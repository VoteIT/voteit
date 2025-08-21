from auditlog.context import set_actor
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_ORG_MANAGER

User = get_user_model()


class AuditlogIntegrationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create(username="superuser")

    def test_create(self):
        with set_actor(self.superuser):
            org: Organisation = Organisation.objects.create(title="Hello")
        entry = LogEntry.objects.get_for_object(org).last()
        self.maxDiff = None
        self.assertEqual(
            {
                "title": ["None", "Hello"],
                "active": ["None", "True"],
                "body": ["None", ""],
                "help_info": ["None", ""],
                "host": ["None", "None"],
                "page_title": ["None", "Hello"],
            },
            entry.changes_dict,
        )

    def test_create_roles(self):
        with set_actor(self.superuser):
            org: Organisation = Organisation.objects.create(title="Hello")
            org.add_roles(self.superuser, ROLE_ORG_MANAGER)
        entry = LogEntry.objects.all().first()
        self.assertEqual(
            ("organisation", "organisationroles"), entry.content_type.natural_key()
        )
        # This is not what we want
        self.assertEqual(
            {"assigned": ["[]", "{Organisation manager (org_manager)}"]},
            entry.changes_dict,
        )
