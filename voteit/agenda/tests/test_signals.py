from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.messaging.messages.channels import Subscribe

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SubscribedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()
        self.ai_private = self.meeting.agenda_items.create()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "moderator")

    def test_app_state_sent_participants(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=ParticipantsChannel.name,
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "agenda_item.added"])
        self.assertEqual({self.ai.pk}, pks)

    def test_app_state_sent_moderators(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=ModeratorsChannel.name,
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "agenda_item.added"])
        self.assertEqual({self.ai.pk, self.ai_private.pk}, pks)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AgendaChangedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()

    @patch.object(ParticipantsChannel, "publish")
    def test_added_participants(self, mock_publish):
        # This should have no effect at all
        self.assertFalse(mock_publish.called)
        self.meeting.agenda_items.create()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "publish")
    def test_added_moderators(self, mock_publish):
        from voteit.agenda.messages import AgendaAdded

        self.assertFalse(mock_publish.called)
        ai = self.meeting.agenda_items.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaAdded)
        self.assertEqual(ai.pk, msg.data.pk)

    @patch.object(ParticipantsChannel, "publish")
    def test_changed_participants(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged
        from voteit.agenda.messages import AgendaDeleted

        self.assertFalse(mock_publish.called)
        self.ai.title = "Hello"
        self.ai.save()
        # Still private, so deleted was sent here
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaDeleted)
        self.assertEqual(self.ai.pk, msg.data.pk)
        self.ai.upcoming()
        self.ai.save()
        # But now it's published
        msg = mock_publish.mock_calls[1].args[0]
        self.assertIsInstance(msg, AgendaChanged)
        self.assertEqual(self.ai.pk, msg.data.pk)

    @patch.object(ParticipantsChannel, "publish")
    def test_deleted_participants(self, mock_publish):
        from voteit.agenda.messages import AgendaDeleted

        self.ai.delete()
        self.assertFalse(mock_publish.called)
        # Create a new item
        ai = self.meeting.agenda_items.create()
        ai.upcoming()
        ai.save()
        mock_publish.reset_mock()
        ai_pk = ai.pk
        ai.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaDeleted)
        self.assertEqual(ai_pk, msg.data.pk)

    @patch.object(ModeratorsChannel, "publish")
    def test_deleted_moderators(self, mock_publish):
        from voteit.agenda.messages import AgendaDeleted

        self.assertFalse(mock_publish.called)
        ai_pk = self.ai.pk
        self.ai.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaDeleted)
        self.assertEqual(ai_pk, msg.data.pk)


class ArchiveAgendaTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.meeting.agenda_items.create()

    def test_archive(self):
        self.meeting.archive()
        ai = self.meeting.agenda_items.first()
        self.assertEqual("archived", ai.state)
