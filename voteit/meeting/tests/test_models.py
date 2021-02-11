from django.contrib.auth import get_user_model
from django.test import TestCase


class MeetingTests(TestCase):
    @property
    def Meeting(self):
        from voteit.meeting.models import Meeting

        return Meeting

    def test_workflow_transitions(self):
        meeting = self.Meeting.objects.create(er_policy_name="auto_before_poll")
        meeting.ongoing()
        meeting.upcoming()
        meeting.ongoing()
        meeting.close()
        meeting.ongoing()
        meeting.close()
        meeting.request_archiving()
        meeting.abort_archiving()
        meeting.archive()
        self.assertEqual("archived", meeting.state)

    def test_er_policy(self):
        from voteit.poll.app.er_policys.auto_before_poll import AutoBeforePoll

        meeting = self.Meeting.objects.create(er_policy_name=AutoBeforePoll.name)
        self.assertIsInstance(meeting.er_policy, AutoBeforePoll)

    def test_get_latest_er(self):
        from voteit.poll.models import ElectoralRegister

        meeting = self.Meeting.objects.create()
        self.assertIsNone(meeting.get_latest_er())
        er1 = ElectoralRegister.objects.create(meeting=meeting)
        self.assertEqual(er1, meeting.get_latest_er())
        er2 = ElectoralRegister.objects.create(meeting=meeting)
        self.assertEqual(er2, meeting.get_latest_er())

    def test_get_access_policies(self):
        from voteit.access_policy.app.policies.automatic import AutomaticAccess

        meeting = self.Meeting.objects.create()
        self.assertEqual(set(), set(meeting.get_access_policies()))
        AutomaticAccess.objects.create(meeting=meeting, active=True)
        found = list(meeting.get_access_policies())
        self.assertEqual(1, len(found))
        ap_inst = found[0]
        self.assertIsInstance(ap_inst, AutomaticAccess)
        ap_inst.active = False
        ap_inst.save()
        self.assertFalse(list(meeting.get_access_policies()))
        self.assertTrue(list(meeting.get_access_policies(only_active=False)))

    def test_archive_archives_ais(self):
        meeting = self.Meeting.objects.create()
        meeting.agenda_items.create()
        meeting.archive()
        ai = meeting.agenda_items.first()
        self.assertEqual("archived", ai.state)


class ManagerTests(TestCase):
    @property
    def Meeting(self):
        from voteit.meeting.models import Meeting

        return Meeting

    def setUp(self) -> None:
        self.private_meeting = self.Meeting.objects.create()
        self.public_meeting = self.Meeting.objects.create(public=True)

    def test_for_user(self):
        User = get_user_model()
        participant = self.private_meeting.participants.create(username='p')
        non_participant = User.objects.create(username='np')
        self.assertEqual(
            self.Meeting.objects.for_user(participant).count(), 2
        )
        self.assertEqual(
            self.Meeting.objects.for_user(participant).filter(public=False).count(), 1
        )
        self.assertEqual(
            self.Meeting.objects.for_user(non_participant).count(), 1
        )
        self.assertIs(
            self.Meeting.objects.for_user(non_participant).get().public, True
        )
