from django.contrib.auth.models import User
from django.test import TestCase


class AutomaticAPTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a")

    @property
    def _cut(self):
        from voteit.access_policy.app.policies.automatic import AutomaticAccess

        return AutomaticAccess

    def test_set_given_roles(self):
        auto_ap = self._cut.objects.create(
            meeting_aps=self.meeting.access_policies, active=True
        )
        auto_ap.set_given_roles("participant")
        self.assertEqual("participant", auto_ap.roles_given)

    def test_assign(self):
        from voteit.meeting.roles import Participant

        auto_ap = self._cut.objects.create(
            meeting_aps=self.meeting.access_policies, active=True
        )
        participants = Participant(self.meeting)
        self.assertNotIn(self.user, participants)
        auto_ap.assign(self.user)
        self.assertNotIn(self.user, participants)
        auto_ap.set_given_roles("participant")
        auto_ap.assign(self.user)
        self.assertIn(self.user, participants)

    def test_get_valid_roles(self):
        from voteit.core.role import Role
        from voteit.meeting.roles import Participant

        auto_ap = self._cut.objects.create(
            meeting_aps=self.meeting.access_policies, active=True
        )
        roles = auto_ap.get_valid_roles()
        self.assertIn(Participant, roles)
        for role in roles:
            self.assertTrue(issubclass(role, Role))
