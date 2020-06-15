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


class PermissionTests(TestCase):
    def setUp(self):
        from voteit.organisation.models import Organisation
        self.org = Organisation.objects.create()
        self.anon_user = User.objects.create(username="anon")
        self.meeting_creator = self.org.meeting_creators.create(username="meeting_creator")
        self.manager = self.org.managers.create(username="manager")

    def test_can_add_meeting(self):
        from voteit.meeting.permissions import MeetingPermissions
        self.assertFalse(self.anon_user.has_perm(MeetingPermissions.ADD, self.org))
        self.assertTrue(self.meeting_creator.has_perm(MeetingPermissions.ADD, self.org))
        self.assertTrue(self.manager.has_perm(MeetingPermissions.ADD, self.org))
