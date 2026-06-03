from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.active.components import ActiveUsersComponent
from voteit.active.models import ActiveUser
from voteit.core import PERM
from voteit.meeting.models import Meeting
from voteit.meeting.workflows import MeetingWf

User = get_user_model()


class ActiveUserPermissionsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.component = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.anon_user = User.objects.create(username="anon")

    def test_change(self):
        CHANGE = ActiveUser.get_perm(PERM.CHANGE)
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertTrue(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))

    def test_change_closed_meeting(self):
        self.meeting.state = MeetingWf.CLOSED
        self.meeting.save()
        CHANGE = ActiveUser.get_perm(PERM.CHANGE)
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))

    def test_change_component_not_enabled(self):
        self.component.disable()
        self.component.save()
        CHANGE = ActiveUser.get_perm(PERM.CHANGE)
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))

    def test_view(self):
        VIEW = ActiveUser.get_perm(PERM.VIEW)
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting))
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting))
