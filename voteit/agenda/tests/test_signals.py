from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from pytz import UTC
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.messaging.messages.channels import Subscribe

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem

        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.ai.upcoming()
        cls.ai.save()
        cls.ai_private: AgendaItem = cls.meeting.agenda_items.create()
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, "moderator")
        cls.ai_private.mark_read(cls.user)

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

    def test_app_state_last_read_sent(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=MeetingChannel.name,
        )
        msg = command.run_job()
        agenda_pks = set(
            [
                x.p["agenda_item"]
                for x in msg.data.app_state
                if x.t == "last_read.changed"
            ]
        )
        self.assertEqual({self.ai_private.pk}, agenda_pks)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AgendaChangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai_pk = cls.ai.pk

    def setUp(self):
        self.ai = self.meeting.agenda_items.get(pk=self.ai_pk)

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


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class RelatedItemsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem

        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(state="upcoming")
        cls.prop = cls.ai.proposals.create()
        cls.prop.modified = datetime(2021, 1, 1, 12, 0, tzinfo=UTC)
        cls.prop.save()
        cls.prop_pk = cls.prop.pk
        cls.disc = cls.ai.discussions.create()
        cls.disc.modified = datetime(2021, 2, 2, 12, 0, tzinfo=UTC)
        cls.disc.save()
        cls.disc_pk = cls.disc.pk
        # Make sure related will be triggered
        cls.ai.related_modified = datetime(2021, 3, 3, 12, 0, tzinfo=UTC)
        cls.ai.save()

    def setUp(self):
        self.prop = self.ai.proposals.get(pk=self.prop_pk)
        self.disc = self.ai.discussions.get(pk=self.disc_pk)
        self.ai.refresh_from_db()

    @patch.object(ParticipantsChannel, "publish")
    def test_proposal_deleted(self, mock_publish):
        self.prop.delete()
        self.assertEqual(
            1,
            len(
                [
                    x.args[0]
                    for x in mock_publish.mock_calls
                    if x.args[0].name == "agenda_item.changed"
                ]
            ),
        )

    @patch.object(ParticipantsChannel, "publish")
    def test_discussion_deleted(self, mock_publish):
        self.disc.delete()
        self.assertEqual(
            1,
            len(
                [
                    x.args[0]
                    for x in mock_publish.mock_calls
                    if x.args[0].name == "agenda_item.changed"
                ]
            ),
        )

    @patch.object(ParticipantsChannel, "publish")
    def test_proposal_changed(self, mock_publish):
        self.prop.text = "Hello"
        self.prop.save()
        self.assertEqual(
            1,
            len(
                [
                    x.args[0]
                    for x in mock_publish.mock_calls
                    if x.args[0].name == "agenda_item.changed"
                ]
            ),
        )

    @patch.object(ParticipantsChannel, "publish")
    def test_discussion_changed(self, mock_publish):
        self.disc.text = "Hello"
        self.disc.save()
        self.assertEqual(
            1,
            len(
                [
                    x.args[0]
                    for x in mock_publish.mock_calls
                    if x.args[0].name == "agenda_item.changed"
                ]
            ),
        )
