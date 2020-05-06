from django.test import TestCase


class MeetingTests(TestCase):
    @property
    def Meeting(self):
        from voteit.meeting.models import Meeting

        return Meeting

    def test_workflow_transitions(self):
        meeting = self.Meeting.objects.create()
        meeting.ongoing()
        meeting.upcoming()
        meeting.ongoing()
        meeting.closed()
        meeting.ongoing()
        meeting.closed()
        meeting.archived()
        self.assertEqual("archived", meeting.state)

    def test_er_policy(self):
        from voteit.poll.app.er_policys.auto_before_poll import AutoBeforePoll
        meeting = self.Meeting.objects.create()
        er_policy = AutoBeforePoll.objects.create()
        meeting.er_policy = er_policy
        self.assertEqual(er_policy, meeting.er_policy)

    def test_get_latest_er(self):
        from voteit.poll.models import ElectoralRegister

        meeting = self.Meeting.objects.create()
        self.assertIsNone(meeting.get_latest_er())
        er1 = ElectoralRegister.objects.create(meeting=meeting)
        self.assertEqual(er1, meeting.get_latest_er())
        er2 = ElectoralRegister.objects.create(meeting=meeting)
        self.assertEqual(er2, meeting.get_latest_er())
