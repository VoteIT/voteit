from django.contrib.auth.models import User
from django.test import TestCase
from voteit.poll.exceptions import (
    ElectoralRegisterMissing,
    ElectoralRegisterEmpty,
    InvalidProposalCount,
    InvalidPollMethod,
)


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
