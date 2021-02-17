from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.agenda.channels import AgendaItemChannel
from voteit.messaging.messages.channels import Subscribe

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AgendaSubscribedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()
        self.disc1 = self.ai.discussions.create()
        self.disc2 = self.ai.discussions.create()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "participant")

    def test_app_state_sent(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.ai.pk,
            channel_type="agenda_item",
        )
        msg = command.run_job()
        pks = set(
            [x.p["pk"] for x in msg.data.app_state if x.t == "discussion_post.added"]
        )
        self.assertEqual({self.disc1.pk, self.disc2.pk}, pks)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class DiscussionPostChangedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.disc = self.ai.discussions.create()

    @patch.object(AgendaItemChannel, "publish")
    def test_added(self, mock_publish):
        from voteit.discussion.messages import DiscussionPostAdded

        self.assertFalse(mock_publish.called)
        disc = self.ai.discussions.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, DiscussionPostAdded)
        self.assertEqual(disc.pk, msg.data.pk)

    @patch.object(AgendaItemChannel, "publish")
    def test_changed(self, mock_publish):
        from voteit.discussion.messages import DiscussionPostChanged

        self.assertFalse(mock_publish.called)
        self.disc.body = "Hello"
        self.disc.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, DiscussionPostChanged)
        self.assertEqual(self.disc.pk, msg.data.pk)

    @patch.object(AgendaItemChannel, "publish")
    def test_deleted(self, mock_publish):
        from voteit.discussion.messages import DiscussionPostDeleted

        self.assertFalse(mock_publish.called)
        disc_pk = self.disc.pk
        self.disc.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, DiscussionPostDeleted)
        self.assertEqual(disc_pk, msg.data.pk)
