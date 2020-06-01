from django.test import TestCase


class MeetingAccessPoliciesTests(TestCase):
    @property
    def Meeting(self):
        from voteit.meeting.models import Meeting

        return Meeting

    @property
    def _cut(self):
        from voteit.access_policy.models import MeetingAccessPolicies

        return MeetingAccessPolicies

    def test_created_when_meeting_created(self):
        meeting = self.Meeting.objects.create()
        instance = self._cut.objects.get(meeting=meeting)
        self.assertIsInstance(instance, self._cut)
        self.assertEqual(instance.meeting, meeting)

    def test_get_active_policies(self):
        from voteit.access_policy.app.policies.automatic import AutomaticAccess

        meeting = self.Meeting.objects.create()
        aps = meeting.access_policies
        self.assertEqual(set(), set(aps.get_active_policies()))
        AutomaticAccess.objects.create(meeting_aps=aps, active=True)
        found = list(aps.get_active_policies())
        self.assertEqual(1, len(found))
        ap_inst = found[0]
        self.assertIsInstance(ap_inst, AutomaticAccess)
        ap_inst.active = False
        ap_inst.save()
        self.assertFalse(list(aps.get_active_policies()))

    def test_get_policies(self):
        from voteit.access_policy.app.policies.automatic import AutomaticAccess
        from voteit.access_policy.abcs import AccessPolicy

        meeting = self.Meeting.objects.create()
        aps = meeting.access_policies
        policies = list(aps.get_policies())
        self.assertIn(AutomaticAccess, policies)
        for policy in policies:
            self.assertTrue(issubclass(policy, AccessPolicy))
