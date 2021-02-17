from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.meeting.channels import MeetingChannel
from voteit.messaging.messages.channels import Subscribe

User = get_user_model()


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class PollSubscribedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.poll.models import ElectoralRegister

        er = ElectoralRegister.objects.create()
        self.meeting = Meeting.objects.create()
        self.poll = self.meeting.polls.create(
            method_name="simple", electoral_register=er
        )
        self.poll.upcoming()
        self.poll.save()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "participant")

    def test_app_state_sent(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.poll.pk,
            channel_type="poll",
        )
        msg = command.run_job()
        unpacked = dict([(x.t, x.p) for x in msg.data.app_state])
        self.assertIn("poll.status", unpacked)
        self.assertEqual(self.poll.pk, unpacked["poll.status"]["pk"])


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingSubscribedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.poll.models import ElectoralRegister

        er = ElectoralRegister.objects.create()
        self.meeting = Meeting.objects.create()
        self.poll = self.meeting.polls.create(
            method_name="simple", electoral_register=er
        )
        self.poll.upcoming()
        self.poll.save()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "participant")

    def test_app_state_sent(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="meeting",
        )
        msg = command.run_job()
        unpacked = dict([(x.t, x.p) for x in msg.data.app_state])
        self.assertIn("poll.added", unpacked)
        self.assertEqual(self.poll.pk, unpacked["poll.added"]["pk"])


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class PollChangedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.meeting = Meeting.objects.create()
        self.poll = self.meeting.polls.create(
            method_name="simple", electoral_register=self.er
        )
        self.poll.upcoming()
        self.poll.save()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "participant")

    @patch.object(MeetingChannel, "publish")
    def test_added(self, mock_publish):
        from voteit.poll.messages import PollAdded

        self.assertFalse(mock_publish.called)
        poll = self.meeting.polls.create(
            method_name="simple", electoral_register=self.er
        )
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollAdded)
        self.assertEqual(poll.pk, msg.data.pk)

    @patch.object(MeetingChannel, "publish")
    def test_changed(self, mock_publish):
        from voteit.poll.messages import PollChanged

        self.assertFalse(mock_publish.called)
        self.poll.title = "Hello"
        self.poll.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollChanged)
        self.assertEqual(self.poll.pk, msg.data.pk)

    @patch.object(MeetingChannel, "publish")
    def test_deleted(self, mock_publish):
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        poll_pk = self.poll.pk
        self.poll.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(poll_pk, msg.data.pk)
