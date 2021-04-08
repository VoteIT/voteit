from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.meeting.models import Meeting

User = get_user_model()


class InvitesExpireWhenMeetingArchivedTests(TestCase):
    def setUp(self):
        from voteit.access_policy.models import MeetingInvite

        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a")

        self.inv1 = MeetingInvite.objects.create(
            meeting=self.meeting,
            created_by=self.user,
            data={"email": "a@betahaus.net"},
        )

    def test_expire(self):
        from voteit.access_policy.workflows import InviteWf

        self.assertEqual(InviteWf.OPEN, self.inv1.state)
        self.meeting.archive()
        self.inv1.refresh_from_db()
        self.assertEqual(InviteWf.EXPIRED, self.inv1.state)
