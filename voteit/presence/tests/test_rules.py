from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.presence.components import PresenceCheckComponent

User = get_user_model()


class PresenceCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.component = cls.meeting.components.create(
            component_name=PresenceCheckComponent.name, state=EnabledWf.ON
        )
        cls.presence_check = cls.meeting.presence_checks.create()
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.anon_user = User.objects.create(username="anon")

    @property
    def P(self):
        from voteit.presence.permissions import PresenceCheckPermissions

        return PresenceCheckPermissions

    def test_add(self):
        ADD = self.P.ADD
        self.assertIs(self.moderator.has_perm(ADD, self.meeting), True)
        self.assertIs(self.participant.has_perm(ADD, self.meeting), False)
        self.assertIs(self.anon_user.has_perm(ADD, self.meeting), False)

    def test_change_open(self):
        CHANGE = self.P.CHANGE
        self.assertTrue(self.moderator.has_perm(CHANGE, self.presence_check))
        self.assertFalse(self.participant.has_perm(CHANGE, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.presence_check))

    def test_change_closed(self):
        CHANGE = self.P.CHANGE
        self.presence_check.close()
        self.assertFalse(self.moderator.has_perm(CHANGE, self.presence_check))
        self.assertFalse(self.participant.has_perm(CHANGE, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.presence_check))

    def test_delete(self):
        DELETE = self.P.DELETE
        self.assertTrue(self.moderator.has_perm(DELETE, self.presence_check))
        self.assertFalse(self.participant.has_perm(DELETE, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(DELETE, self.presence_check))

    def test_delete_closed(self):
        DELETE = self.P.DELETE
        self.presence_check.close()
        self.assertTrue(self.moderator.has_perm(DELETE, self.presence_check))
        self.assertFalse(self.participant.has_perm(DELETE, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(DELETE, self.presence_check))

    def test_view(self):
        VIEW = self.P.VIEW
        self.assertTrue(self.moderator.has_perm(VIEW, self.presence_check))
        self.assertTrue(self.participant.has_perm(VIEW, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(VIEW, self.presence_check))

    def test_view_public_meeting(self):
        VIEW = self.P.VIEW
        self.meeting.public = True
        self.meeting.save()
        self.assertTrue(self.moderator.has_perm(VIEW, self.presence_check))
        self.assertTrue(self.participant.has_perm(VIEW, self.presence_check))
        self.assertTrue(self.anon_user.has_perm(VIEW, self.presence_check))


class PresenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.component = cls.meeting.components.create(
            component_name=PresenceCheckComponent.name, state=EnabledWf.ON
        )
        cls.presence_check = cls.meeting.presence_checks.create()
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.anon_user = User.objects.create(username="anon")
        cls.present_participant = User.objects.create(username="present_participant")
        cls.meeting.add_roles(cls.present_participant, ROLE_PARTICIPANT)
        cls.presence = cls.presence_check.presences.create(user=cls.present_participant)

    @property
    def P(self):
        from voteit.presence.permissions import PresencePermissions

        return PresencePermissions

    def test_change(self):
        CHANGE = self.P.CHANGE
        self.assertTrue(self.moderator.has_perm(CHANGE, self.presence_check))
        self.assertTrue(self.participant.has_perm(CHANGE, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.presence_check))

    def test_change_closed(self):
        CHANGE = self.P.CHANGE
        self.presence_check.close()
        self.assertFalse(self.moderator.has_perm(CHANGE, self.presence_check))
        self.assertFalse(self.participant.has_perm(CHANGE, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.presence_check))

    def test_view(self):
        VIEW = self.P.VIEW
        self.assertTrue(self.moderator.has_perm(VIEW, self.presence))
        self.assertFalse(self.participant.has_perm(VIEW, self.presence))
        self.assertTrue(self.present_participant.has_perm(VIEW, self.presence))
        self.assertFalse(self.anon_user.has_perm(VIEW, self.presence))
