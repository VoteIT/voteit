from django.test import TestCase
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.rules import is_manager
from voteit.organisation.rules import is_meeting_creator


class RulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.user = cls.org.users.create(username="a")
        cls.roles = OrganisationRoles.objects.create(context=cls.org, user=cls.user)
        cls.ROLES = OrganisationRoles.valid_roles

    def test_is_manager(self):
        manager = self.ROLES["org_manager"]
        self.assertFalse(is_manager(self.user, self.org))
        self.roles.add(manager)
        self.assertTrue(is_manager(self.user, self.org))

    def test_is_meeting_creator(self):
        self.assertFalse(is_meeting_creator(self.user, self.org))
        meeting_creator = self.ROLES["meeting_creator"]
        self.roles.add(meeting_creator)
        self.assertTrue(is_meeting_creator(self.user, self.org))
