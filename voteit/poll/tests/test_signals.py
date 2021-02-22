from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.meeting.channels import ParticipantsChannel, ModeratorsChannel
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
class ParticipantsSubscribedTests(TestCase):
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
        self.poll_private = self.meeting.polls.create(
            method_name="simple", electoral_register=er
        )
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "moderator")

    def test_app_state_sent_participants(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=ParticipantsChannel.name,
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "poll.added"])
        self.assertEqual({self.poll.pk}, pks)

    def test_app_state_sent_moderators(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=ModeratorsChannel.name,
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "poll.added"])
        self.assertEqual({self.poll.pk, self.poll_private.pk}, pks)


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

    @patch.object(ParticipantsChannel, "publish")
    def test_added_participants(self, mock_publish):
        self.meeting.polls.create(method_name="simple", electoral_register=self.er)
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "publish")
    def test_added_moderators(self, mock_publish):
        from voteit.poll.messages import PollAdded

        self.assertFalse(mock_publish.called)
        poll = self.meeting.polls.create(
            method_name="simple", electoral_register=self.er
        )
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollAdded)
        self.assertEqual(poll.pk, msg.data.pk)

    @patch.object(ParticipantsChannel, "publish")
    def test_changed_participants(self, mock_publish):
        from voteit.poll.messages import PollChanged
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        self.poll.title = "Hello"
        self.poll.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollChanged)
        self.assertEqual(self.poll.pk, msg.data.pk)
        mock_publish.reset_mock()
        self.poll.unpublish()
        self.poll.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(self.poll.pk, msg.data.pk)

    @patch.object(ModeratorsChannel, "publish")
    def test_deleted_moderators(self, mock_publish):
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        poll_pk = self.poll.pk
        self.poll.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(poll_pk, msg.data.pk)

    @patch.object(ParticipantsChannel, "publish")
    def test_deleted(self, mock_publish):
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        poll_pk = self.poll.pk
        self.poll.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(poll_pk, msg.data.pk)
        # Creating a new private poll
        poll = self.meeting.polls.create(
            method_name="simple", electoral_register=self.er
        )
        mock_publish.reset_mock()
        poll.delete()
        # Poll was private, so no message sent
        self.assertFalse(mock_publish.called)
