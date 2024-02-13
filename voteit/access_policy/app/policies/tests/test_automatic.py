from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_PROPOSER


class AutomaticAPTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        User = get_user_model()

        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a")

    @property
    def _cut(self):
        from voteit.access_policy.app.policies.automatic import AutomaticAccess

        return AutomaticAccess

    def test_set_given_roles(self):
        auto_ap = self._cut.objects.create(meeting=self.meeting, active=True)
        auto_ap.roles_given = (ROLE_PARTICIPANT,)
        auto_ap.save()
        auto_ap.refresh_from_db()
        self.assertEqual([ROLE_PARTICIPANT], auto_ap.roles_given)

    def test_assign(self):
        auto_ap = self._cut.objects.create(
            meeting=self.meeting, active=True, roles_given=[ROLE_PARTICIPANT]
        )
        self.assertFalse(self.meeting.has_roles(self.user, ROLE_PARTICIPANT))
        auto_ap.assign(self.user)
        self.assertFalse(self.meeting.has_roles(self.user, ROLE_PROPOSER))
        auto_ap.roles_given = (ROLE_PARTICIPANT, ROLE_PROPOSER)
        auto_ap.assign(self.user)
        self.assertTrue(self.meeting.has_roles(self.user, ROLE_PROPOSER))
