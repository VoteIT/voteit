from django.contrib.auth.models import User
from django.test import TestCase


class RulesTests(TestCase):

    def setUp(self):
        from voteit.organisation.models import Organisation, OrganisationRoles
        self.org = Organisation.objects.create()
        self.user = User.objects.create(username="a")
        self.roles = OrganisationRoles.objects.create(context=self.org, user=self.user)
        self.ROLES = OrganisationRoles.valid_roles

    def test_is_manager(self):
        from voteit.organisation.rules import is_manager
        manager = self.ROLES["org_manager"]
        self.assertFalse(is_manager(self.user, self.org))
        self.roles.add(manager)
        self.assertTrue(is_manager(self.user, self.org))

    def test_is_meeting_creator(self):
        from voteit.organisation.rules import is_meeting_creator
        self.assertFalse(is_meeting_creator(self.user, self.org))
        meeting_creator = self.ROLES["meeting_creator"]
        self.roles.add(meeting_creator)
        self.assertTrue(is_meeting_creator(self.user, self.org))
