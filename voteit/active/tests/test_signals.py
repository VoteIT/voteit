from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import action_of
from voteit.messaging.testing import build_app_state
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.active.components import ActiveUsersComponent
from voteit.active.messages import ActiveUserChanged
from voteit.active.messages import ActiveUsers
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.create(username="participant")
        cls.active_user = User.objects.create(username="active")
        cls.meeting: Meeting = Meeting.objects.create()
        cls.component = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.active_user, ROLE_PARTICIPANT)
        cls.active = cls.meeting.active_users.create(user=cls.active_user)

    def _mk_msg(self):
        return build_app_state(
            MeetingChannel.name, self.meeting.pk, self.participant.pk
        )

    @patch.object(MeetingChannel, "sync_publish")
    def test_changed(self, mock_publish):
        obj = self.meeting.active_users.create(user=self.participant)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ActiveUserChanged)
        self.assertEqual(msg.payload.user, self.participant.pk)
        self.assertEqual(msg.payload.meeting, self.meeting.pk)
        self.assertTrue(msg.payload.active)
        mock_publish.reset_mock()
        obj.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ActiveUserChanged)
        self.assertEqual(msg.payload.user, self.participant.pk)
        self.assertEqual(msg.payload.meeting, self.meeting.pk)
        self.assertFalse(msg.payload.active)

    def test_meeting_channel_subscribed(self):
        msg = self._mk_msg()
        app_state = msg
        active_msgs = [x for x in app_state if x.action == action_of(ActiveUsers)]
        self.assertEqual(1, len(active_msgs))
        msg_dict = active_msgs[0]
        self.assertEqual([self.active.user_id], msg_dict["p"].users)

    def test_meeting_channel_subscribed_not_sent_when_disabled(self):
        self.component.delete()
        msg = self._mk_msg()
        app_state = msg
        self.assertEqual(
            [], [x for x in app_state if x.action == action_of(ActiveUsers)]
        )

    @patch.object(MeetingChannel, "sync_publish")
    def test_enable_disable_component(self, mock_publish):
        with self.captureOnCommitCallbacks(execute=True):
            self.component.disable()
            self.component.save()
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len(messages))  # Deleted

        mock_publish.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            self.component.enable()
            self.component.save()

        self.assertEqual(1, len(messages))  # Created
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ActiveUsers)
        self.assertEqual(msg.payload.users, [self.active_user.pk])
        self.assertEqual(msg.payload.meeting, self.meeting.pk)

    def test_removing_user_from_meeting_removes_active(self):
        self.meeting.remove_roles(self.active_user, ROLE_PARTICIPANT)
        with self.assertRaises(self.active.DoesNotExist):
            self.active.refresh_from_db()
