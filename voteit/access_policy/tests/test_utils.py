from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class GetPoliciesTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.access_policy.app.policies import (
            AutomaticAccess,
            ModeratorApprovedAccess,
        )

        self.meeting = Meeting.objects.create()
        auto_ap = AutomaticAccess.objects.create(meeting=self.meeting)
        mod_ap = ModeratorApprovedAccess.objects.create(
            meeting=self.meeting, active=True
        )

    @property
    def _fut(self):
        from voteit.access_policy.utils import get_policies

        return get_policies

    def test_function(self):
        self.assertEqual(
            {"moderator_approved"}, {x.name for x in self._fut(self.meeting)}
        )
        self.assertEqual(
            {"automatic", "moderator_approved"},
            {x.name for x in self._fut(self.meeting, only_active=False)},
        )
