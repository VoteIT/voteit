from unittest.mock import patch

from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.app.user_channel.channel import UserChannel
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed

from voteit.core.testing import FakeCommit
from voteit.core.workflows import EnabledWf
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.presence.channels import PresenceCheckChannel
from voteit.presence.components import PresenceCheckComponent
from voteit.presence.models import PresenceCheck

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="creeper")
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting = Meeting.objects.create()
        cls.component = cls.meeting.components.create(
            component_name=PresenceCheckComponent.name, state=EnabledWf.ON
        )
        cls.meeting.add_roles(cls.user, "participant")
        cls.meeting.add_roles(cls.moderator, "moderator")
        cls.check = PresenceCheck.objects.create(meeting=cls.meeting)

    def setUp(self):
        self.check.refresh_from_db()

    def _mk_presence(self):
        from voteit.presence.models import Presence

        return Presence.objects.create(user=self.user, presence_check=self.check)

    @patch.object(UserChannel, "sync_publish")
    def test_presence_add_user_channel(self, mock_publish):
        from voteit.presence.messages import PresenceAdded

        presence = self._mk_presence()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PresenceAdded)
        self.assertEqual(msg.data.user, self.user.pk)
        self.assertEqual(msg.data.pk, presence.pk)

    @patch.object(PresenceCheckChannel, "sync_publish")
    def test_presence_add_presence_channel(self, mock_publish):
        from voteit.presence.messages import PresenceAdded

        self._mk_presence()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PresenceAdded)
        self.assertEqual(msg.data.user, self.user.pk)
        self.assertEqual(msg.data.presence_check, self.check.pk)

    @patch.object(UserChannel, "sync_publish")
    def test_presence_deleted_user_channel(self, mock_publish):
        from voteit.presence.messages import PresenceDeleted

        presence = self._mk_presence()
        presence_pk = presence.pk
        mock_publish.reset_mock()
        presence.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PresenceDeleted)
        self.assertEqual(msg.data.pk, presence_pk)

    @patch.object(PresenceCheckChannel, "sync_publish")
    def test_presence_deleted_presence_channel(self, mock_publish):
        from voteit.presence.messages import PresenceDeleted

        presence = self._mk_presence()
        mock_publish.reset_mock()
        presence.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PresenceDeleted)
        self.assertEqual(msg.data.user, self.user.pk)
        self.assertEqual(msg.data.presence_check, self.check.pk)

    def test_meeting_channel_subscribed(self):
        self._mk_presence()
        channel_layer = get_channel_layer()

        with patch.object(channel_layer, "send") as mocked_send:
            with FakeCommit():
                msg = Subscribe(
                    mm={"user_pk": self.user.pk, "consumer_name": "abc"},
                    channel_type=MeetingChannel.name,
                    pk=self.meeting.pk,
                )
                response = msg.run_job()
            self.assertTrue(mocked_send.called)
        self.assertIsInstance(response, Subscribed)
        found = [x for x in response.data.app_state if x.t == "presence.added"]
        self.assertEqual(1, len(found))
        outgoing = found[0]
        self.assertEqual(self.check.pk, outgoing.p["presence_check"])
        self.assertEqual(self.user.pk, outgoing.p["user"])

    @patch.object(MeetingChannel, "sync_publish")
    def test_meeting_channel_subscribed_no_presence_check(self, mock_publish):
        self.check.delete()
        mock_publish.reset_mock()
        channel_layer = get_channel_layer()

        with patch.object(channel_layer, "send") as mocked_send:
            with FakeCommit():
                msg = Subscribe(
                    mm={"user_pk": self.moderator.pk, "consumer_name": "abc"},
                    channel_type=MeetingChannel.name,
                    pk=self.meeting.pk,
                )
                response = msg.run_job()
            self.assertTrue(mocked_send.called)
        self.assertIsInstance(response, Subscribed)
        # Nothing breaks

    def test_presence_check_channel_subscribed(self):
        self._mk_presence()
        self.check.presences.create(user=self.moderator)
        channel_layer = get_channel_layer()

        with patch.object(channel_layer, "send") as mocked_send:
            with FakeCommit():
                msg = Subscribe(
                    mm={"user_pk": self.moderator.pk, "consumer_name": "abc"},
                    channel_type=PresenceCheckChannel.name,
                    pk=self.check.pk,
                )
                response = msg.run_job()
            self.assertTrue(mocked_send.called)
        self.assertIsInstance(response, Subscribed)
        found = sorted(
            [x for x in response.data.app_state if x.t == "presence.added"],
            key=lambda x: x.p["pk"],
        )
        self.assertEqual(2, len(found))
        outgoing = found[0]
        self.assertEqual(self.check.pk, outgoing.p["presence_check"])
        self.assertEqual(self.user.pk, outgoing.p["user"])
