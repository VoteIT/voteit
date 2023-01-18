from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.active.components import ActiveUsersComponent
from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.workflows import MeetingWf

User = get_user_model()


class ActiveUserPermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.component = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, state=EnabledWf.ON
        )
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.anon_user = User.objects.create(username="anon")

    @property
    def P(self):
        from voteit.active.permissions import ActiveUserPermissions

        return ActiveUserPermissions

    def test_change(self):
        CHANGE = self.P.CHANGE
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertTrue(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))

    def test_change_closed_meeting(self):
        self.meeting.state = MeetingWf.CLOSED
        self.meeting.save()
        CHANGE = self.P.CHANGE
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))

    def test_change_component_not_enabled(self):
        self.component.disable()
        self.component.save()
        CHANGE = self.P.CHANGE
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))

    def test_view(self):
        VIEW = self.P.VIEW
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting))
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting))
