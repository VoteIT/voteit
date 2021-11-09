from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class PresenceSystemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.presence.models import PresenceSystem
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.meeting = Meeting.objects.create()
        cls.system = PresenceSystem.objects.create(meeting=cls.meeting)
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.anon_user = User.objects.create(username="anon")

    @property
    def P(self):
        from voteit.presence.permissions import PresenceSystemPermissions

        return PresenceSystemPermissions

    def test_add(self):
        ADD = self.P.ADD
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))

    def test_change(self):
        CHANGE = self.P.CHANGE
        self.assertTrue(self.moderator.has_perm(CHANGE, self.system))
        self.assertFalse(self.participant.has_perm(CHANGE, self.system))
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.system))

    def test_delete(self):
        DELETE = self.P.DELETE
        self.assertTrue(self.moderator.has_perm(DELETE, self.system))
        self.assertFalse(self.participant.has_perm(DELETE, self.system))
        self.assertFalse(self.anon_user.has_perm(DELETE, self.system))

    def test_view(self):
        VIEW = self.P.VIEW
        self.assertTrue(self.moderator.has_perm(VIEW, self.system))
        self.assertTrue(self.participant.has_perm(VIEW, self.system))
        self.assertFalse(self.anon_user.has_perm(VIEW, self.system))


class PresenceCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.presence.models import PresenceSystem
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.meeting = Meeting.objects.create()
        cls.system = PresenceSystem.objects.create(meeting=cls.meeting)
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
        from voteit.presence.models import PresenceSystem
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.meeting = Meeting.objects.create()
        cls.system = PresenceSystem.objects.create(meeting=cls.meeting)
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

    def test_add(self):
        ADD = self.P.ADD
        self.assertTrue(self.moderator.has_perm(ADD, self.presence_check))
        self.assertTrue(self.participant.has_perm(ADD, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(ADD, self.presence_check))

    def test_add_closed(self):
        ADD = self.P.ADD
        self.presence_check.close()
        self.assertFalse(self.moderator.has_perm(ADD, self.presence_check))
        self.assertFalse(self.participant.has_perm(ADD, self.presence_check))
        self.assertFalse(self.anon_user.has_perm(ADD, self.presence_check))

    def test_delete(self):
        DELETE = self.P.DELETE
        self.assertTrue(self.moderator.has_perm(DELETE, self.presence))
        self.assertFalse(self.participant.has_perm(DELETE, self.presence))
        self.assertTrue(self.present_participant.has_perm(DELETE, self.presence))
        self.assertFalse(self.anon_user.has_perm(DELETE, self.presence))

    def test_delete_closed(self):
        DELETE = self.P.DELETE
        self.presence_check.close()
        self.assertFalse(self.moderator.has_perm(DELETE, self.presence))
        self.assertFalse(self.participant.has_perm(DELETE, self.presence))
        self.assertFalse(self.present_participant.has_perm(DELETE, self.presence))
        self.assertFalse(self.anon_user.has_perm(DELETE, self.presence))

    def test_view(self):
        VIEW = self.P.VIEW
        self.assertTrue(self.moderator.has_perm(VIEW, self.presence))
        self.assertFalse(self.participant.has_perm(VIEW, self.presence))
        self.assertTrue(self.present_participant.has_perm(VIEW, self.presence))
        self.assertFalse(self.anon_user.has_perm(VIEW, self.presence))
