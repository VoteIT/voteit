from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.meeting.models import Meeting
from voteit.messaging.errors import UnauthorizedError

User = get_user_model()


class MeetingRolesTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create(username="abel")
        self.user_b = User.objects.create(username="bret")
        self.user_c = User.objects.create(username="cain")
        self.meeting = Meeting.objects.create()

    def test_get_meeting_roles_unauthorized(self):
        self.meeting.add_roles(self.user_a, "participant", "moderator")
        from voteit.messaging.messages.roles import GetMeetingRoles

        msg = GetMeetingRoles({}, pk=self.meeting.pk)
        self.assertRaises(UnauthorizedError, msg.run_job)

    # @patch("voteit.messaging.messages.roles.AssignedMeetingRolesResponse", "send_outgoing")
    def test_get_meeting_roles(self):
        self.meeting.add_roles(self.user_a, "participant", "moderator")
        from voteit.messaging.messages.roles import GetMeetingRoles
        from voteit.messaging.messages.roles import AssignedMeetingRolesResponse

        msg = GetMeetingRoles({"user_pk": self.user_a.pk}, pk=self.meeting.pk)

        with patch.object(AssignedMeetingRolesResponse, "send_outgoing") as mock_method:
            response = msg.run_job()
            self.assertTrue(mock_method.called)
            self.assertIsInstance(response, AssignedMeetingRolesResponse)

            res_dict = response.data.dict()
            self.assertEqual(1, len(res_dict["items"]))
            res_items = res_dict["items"]
            self.assertEqual(
                {self.user_a.pk: ['participant', 'moderator']},
                res_items,
            )
