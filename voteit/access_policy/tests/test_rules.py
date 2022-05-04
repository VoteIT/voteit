from django.contrib.auth import get_user_model
from django.test import TestCase


class AutomaticAccessRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.meeting.roles import ROLE_PARTICIPANT
        from voteit.access_policy.app.policies import AutomaticAccess

        User = get_user_model()
        cls.anon_user = User.objects.create(username="anon")
        cls.meeting: Meeting = Meeting.objects.create()
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.policy = AutomaticAccess.objects.create(meeting=cls.meeting)

    def setUp(self):
        self.meeting.refresh_from_db()

    def p(self, perm):
        from voteit.access_policy.permissions import AutomaticAccessPermissions

        return getattr(AutomaticAccessPermissions, perm)

    def _archive(self):
        self.meeting.archive()
        self.meeting.save()

    def test_view(self):
        VIEW = self.p("VIEW")
        self.assertFalse(self.participant.has_perm(VIEW, self.policy))
        self.assertFalse(self.anon_user.has_perm(VIEW, self.policy))
        self.assertTrue(self.moderator.has_perm(VIEW, self.policy))

    def test_add(self):
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_archived_meeting(self):
        self._archive()
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change(self):
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.policy))
        self.assertFalse(self.participant.has_perm(CHANGE, self.policy))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.policy))

    def test_change_archived_meeting(self):
        self._archive()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.policy))
        self.assertFalse(self.participant.has_perm(CHANGE, self.policy))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.policy))

    def test_delete(self):
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.policy))
        self.assertFalse(self.participant.has_perm(DELETE, self.policy))
        self.assertTrue(self.moderator.has_perm(DELETE, self.policy))

    def test_delete_archived_meeting(self):
        self._archive()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.policy))
        self.assertFalse(self.participant.has_perm(DELETE, self.policy))
        self.assertFalse(self.moderator.has_perm(DELETE, self.policy))
