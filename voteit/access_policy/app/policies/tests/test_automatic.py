from django.contrib.auth.models import User
from django.test import TestCase

from voteit.meeting.roles import ROLE_PARTICIPANT


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
            meeting=self.meeting, active=True
        )
        auto_ap.set_given_roles("participant")
        self.assertEqual("participant", auto_ap.roles_given)

    def test_assign(self):

        auto_ap = self._cut.objects.create(
            meeting=self.meeting, active=True
        )
        # participants = Participant(self.meeting)
        self.assertFalse(self.meeting.has_roles(self.user, ROLE_PARTICIPANT))
        auto_ap.assign(self.user)
        self.assertFalse(self.meeting.has_roles(self.user, ROLE_PARTICIPANT))
        auto_ap.set_given_roles("participant")
        auto_ap.assign(self.user)
        self.assertTrue(self.meeting.has_roles(self.user, ROLE_PARTICIPANT))
