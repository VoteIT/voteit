from django.contrib.auth.models import User
from django.test import TestCase


class RulesTests(TestCase):

    def setUp(self):
        from voteit.organisation.models import Organisation
        self.org = Organisation.objects.create()
        self.user = User.objects.create(username="a")

    def test_is_manager(self):
        from voteit.organisation.rules import is_manager
        self.assertFalse(is_manager(self.user, self.org))
        self.org.managers.add(self.user)
        self.org.save()
        self.assertTrue(is_manager(self.user, self.org))

    def test_is_meeting_creator(self):
        from voteit.organisation.rules import is_meeting_creator
        self.assertFalse(is_meeting_creator(self.user, self.org))
        self.org.meeting_creators.add(self.user)
        self.org.save()
        self.assertTrue(is_meeting_creator(self.user, self.org))
