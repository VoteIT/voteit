from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now

from voteit.meeting.jobs import DELETE_AFTER_DAYS
from voteit.meeting.jobs import delete_requested_meetings
from voteit.meeting.models import Meeting
from voteit.meeting.statemachines import MeetingStateMachine
from voteit.organisation.models import Organisation
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll


class DeleteRequestedMeetingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="Org", host="org.voteit.se")
        cls.long_ago = now() - timedelta(days=DELETE_AFTER_DAYS + 1)
        cls.recently = now() - timedelta(days=DELETE_AFTER_DAYS - 1)

    def mk_meeting(self, **kwargs) -> Meeting:
        kwargs.setdefault("state", MeetingStateMachine.deleting.value)
        kwargs.setdefault("delete_requested", self.long_ago)
        return Meeting.objects.create(
            title="Meeting",
            organisation=self.org,
            er_policy_name=AutoBeforePoll.name,
            **kwargs,
        )

    def test_deletes_when_requested_long_ago(self):
        meeting = self.mk_meeting()
        self.assertEqual(1, delete_requested_meetings())
        self.assertFalse(Meeting.objects.filter(pk=meeting.pk).exists())

    def test_keeps_when_requested_recently(self):
        meeting = self.mk_meeting(delete_requested=self.recently)
        self.assertEqual(0, delete_requested_meetings())
        self.assertTrue(Meeting.objects.filter(pk=meeting.pk).exists())

    def test_keeps_without_delete_requested(self):
        meeting = self.mk_meeting(delete_requested=None)
        self.assertEqual(0, delete_requested_meetings())
        self.assertTrue(Meeting.objects.filter(pk=meeting.pk).exists())

    def test_keeps_meeting_with_start_time(self):
        meeting = self.mk_meeting(start_time=self.long_ago)
        self.assertEqual(0, delete_requested_meetings())
        self.assertTrue(Meeting.objects.filter(pk=meeting.pk).exists())

    def test_keeps_other_states(self):
        meeting = self.mk_meeting(state=MeetingStateMachine.archived.value)
        self.assertEqual(0, delete_requested_meetings())
        self.assertTrue(Meeting.objects.filter(pk=meeting.pk).exists())
