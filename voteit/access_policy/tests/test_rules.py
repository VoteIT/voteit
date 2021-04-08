from django.contrib.auth import get_user_model
from django.test import TestCase


class MeetingInvitePermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT
        from voteit.access_policy.models import MeetingInvite
        from voteit.access_policy.workflows import InviteWf

        cls.meeting = Meeting.objects.create(er_policy_name="auto_always")
        User = get_user_model()
        cls.anon_user = User.objects.create(username="anon")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.invite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            created_by=cls.moderator,
            data={"email": "yeah@betahaus.net"},
        )
        cls.wf = InviteWf

    def setUp(self):
        self.meeting.refresh_from_db()
        self.invite.refresh_from_db()

    def p(self, perm):
        from voteit.access_policy.permissions import MeetingInvitePermissions

        return getattr(MeetingInvitePermissions, perm)

    def _archive(self):
        self.meeting.ongoing()
        self.meeting.close()
        self.meeting.archive()
        self.meeting.save()
        self.invite.refresh_from_db()  # will be expired

    def test_view(self):
        PERM = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(PERM, self.invite))
        self.assertFalse(self.participant.has_perm(PERM, self.invite))
        self.assertTrue(self.moderator.has_perm(PERM, self.invite))

    def test_add(self):
        PERM = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(PERM, self.meeting))
        self.assertFalse(self.participant.has_perm(PERM, self.meeting))
        self.assertTrue(self.moderator.has_perm(PERM, self.meeting))

    def test_add_archived_meeting(self):
        self._archive()
        PERM = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(PERM, self.meeting))
        self.assertFalse(self.participant.has_perm(PERM, self.meeting))
        self.assertFalse(self.moderator.has_perm(PERM, self.meeting))

    def test_change(self):
        PERM = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(PERM, self.invite))
        self.assertFalse(self.participant.has_perm(PERM, self.invite))
        self.assertTrue(self.moderator.has_perm(PERM, self.invite))

    def test_change_archived_meeting(self):
        self._archive()
        PERM = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(PERM, self.invite))
        self.assertFalse(self.participant.has_perm(PERM, self.invite))
        self.assertFalse(self.moderator.has_perm(PERM, self.invite))

    def test_change_used_invite(self):
        self.invite.state = self.wf.ACCEPTED
        PERM = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(PERM, self.invite))
        self.assertFalse(self.participant.has_perm(PERM, self.invite))
        self.assertFalse(self.moderator.has_perm(PERM, self.invite))

    def test_delete(self):
        PERM = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(PERM, self.invite))
        self.assertFalse(self.participant.has_perm(PERM, self.invite))
        self.assertTrue(self.moderator.has_perm(PERM, self.invite))

    def test_delete_archived_meeting(self):
        self._archive()
        PERM = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(PERM, self.invite))
        self.assertFalse(self.participant.has_perm(PERM, self.invite))
        self.assertFalse(self.moderator.has_perm(PERM, self.invite))

    def test_delete_used_invite(self):
        self.invite.state = self.wf.ACCEPTED
        PERM = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(PERM, self.invite))
        self.assertFalse(self.participant.has_perm(PERM, self.invite))
        self.assertFalse(self.moderator.has_perm(PERM, self.invite))
