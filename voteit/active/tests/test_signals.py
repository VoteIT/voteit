from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.messages.channels import Subscribe

from voteit.active.components import ActiveUsersComponent
from voteit.active.messages import ActiveUserChanged
from voteit.active.messages import ActiveUsers
from voteit.core.workflows import EnabledWf
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.create(username="participant")
        cls.active = User.objects.create(username="active")
        cls.meeting: Meeting = Meeting.objects.create()
        cls.component = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, state=EnabledWf.ON
        )
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.active = cls.meeting.active_users.create(user=cls.active)

    def _mk_msg(self):
        return Subscribe(
            mm={"user_pk": self.participant.pk, "consumer_name": "abc"},
            channel_type=MeetingChannel.name,
            pk=self.meeting.pk,
        )

    @patch.object(MeetingChannel, "sync_publish")
    def test_changed(self, mock_publish):
        obj = self.meeting.active_users.create(user=self.participant)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ActiveUserChanged)
        self.assertEqual(msg.data.user, self.participant.pk)
        self.assertTrue(msg.data.active)
        mock_publish.reset_mock()
        obj.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ActiveUserChanged)
        self.assertEqual(msg.data.user, self.participant.pk)
        self.assertFalse(msg.data.active)

    def test_meeting_channel_subscribed(self):
        msg = self._mk_msg()
        ch = MeetingChannel.from_instance(self.meeting)
        app_state = msg.get_app_state(ch)
        active_msgs = [x for x in app_state if x["t"] == ActiveUsers.name]
        self.assertEqual(1, len(active_msgs))
        msg_dict = active_msgs[0]
        self.assertEqual([self.active.user_id], msg_dict["p"].users)

    def test_meeting_channel_subscribed_not_sent_when_disabled(self):
        self.component.delete()
        msg = self._mk_msg()
        ch = MeetingChannel.from_instance(self.meeting)
        app_state = msg.get_app_state(ch)
        self.assertEqual([], [x for x in app_state if x["t"] == ActiveUsers.name])
