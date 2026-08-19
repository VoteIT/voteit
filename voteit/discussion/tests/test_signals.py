from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.messaging.testing import build_app_state

from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AgendaSubscribedTests(TestCase):
    def setUp(self):
        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.state = "upcoming"
        self.ai.save()
        self.disc1 = self.ai.discussions.create()
        self.disc2 = self.ai.discussions.create()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, ROLE_PARTICIPANT)

    def test_app_state_sent(self):
        app_state = build_app_state("agenda_item", self.ai.pk, self.user.pk)
        batched_payload = [
            x.payload.items
            for x in app_state
            if x.action == "discussion_post.changed.batch"
        ]
        self.assertEqual(1, len(batched_payload))
        payloads = batched_payload[0]
        self.assertEqual({self.disc1.pk, self.disc2.pk}, {x.pk for x in payloads})


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class DiscussionPostChangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.disc = cls.ai.discussions.create()

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.discussion.messages import DiscussionPostChanged

        self.assertFalse(mock_publish.called)
        disc = self.ai.discussions.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, DiscussionPostChanged)
        self.assertEqual(disc.pk, msg.payload.pk)

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_changed(self, mock_publish):
        from voteit.discussion.messages import DiscussionPostChanged

        self.assertFalse(mock_publish.called)
        self.disc.body = "Hello"
        self.disc.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, DiscussionPostChanged)
        self.assertEqual(self.disc.pk, msg.payload.pk)

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_deleted(self, mock_publish):
        from voteit.discussion.messages import DiscussionPostDeleted

        self.assertFalse(mock_publish.called)
        disc_pk = self.disc.pk
        self.disc.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, DiscussionPostDeleted)
        self.assertEqual(disc_pk, msg.payload.pk)
