from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core import PERM
from voteit.invites.models import MeetingInvite
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT


class MeetingInvitePermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(er_policy_name="auto_always")
        User = get_user_model()
        cls.anon_user = User.objects.create(username="anon")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.invite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            user_data={"email": "yeah@betahaus.net"},
        )

    def setUp(self):
        self.meeting.refresh_from_db()
        self.invite.refresh_from_db()

    def _archive(self):
        self.meeting.state = "closed"
        self.meeting.archive()
        self.meeting.save()
        self.invite.refresh_from_db()  # will be expired

    def test_add(self):
        ADD = MeetingInvite.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_archived_meeting(self):
        self._archive()
        ADD = MeetingInvite.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change(self):
        CHANGE = MeetingInvite.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.invite))
        self.assertFalse(self.participant.has_perm(CHANGE, self.invite))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.invite))

    def test_change_archived_meeting(self):
        self._archive()
        CHANGE = MeetingInvite.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.invite))
        self.assertFalse(self.participant.has_perm(CHANGE, self.invite))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.invite))

    def test_delete(self):
        DELETE = MeetingInvite.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.invite))
        self.assertFalse(self.participant.has_perm(DELETE, self.invite))
        self.assertTrue(self.moderator.has_perm(DELETE, self.invite))

    def test_delete_archived_meeting(self):
        self._archive()
        DELETE = MeetingInvite.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.invite))
        self.assertFalse(self.participant.has_perm(DELETE, self.invite))
        self.assertFalse(self.moderator.has_perm(DELETE, self.invite))
