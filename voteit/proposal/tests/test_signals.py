from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.agenda.channels import AgendaItemChannel

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.messages.channels import Subscribe

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingSubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai.upcoming()
        cls.ai.save()
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, "moderator")

    def setUp(self):
        self.ai.refresh_from_db()

    def test_app_state_sent_moderators(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="moderators",
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "proposal.added"])
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_app_state_sent_private_moderators(self):
        self.ai.unpublish()
        self.ai.save()
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="moderators",
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "proposal.added"])
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_app_state_sent_participants(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="participants",
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "proposal.added"])
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_app_state_sent_private_participants(self):
        self.ai.unpublish()
        self.ai.save()
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="participants",
        )
        msg = command.run_job()
        app_state = msg.data.app_state
        if app_state is None:
            app_state = ()
        pks = set([x.p["pk"] for x in app_state if x.t == "proposal.added"])
        self.assertEqual(set(), pks)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ProposalChangedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()
        self.prop = self.ai.proposals.create()

    @patch.object(ParticipantsChannel, "publish")
    def test_added_participant(self, mock_publish):
        from voteit.proposal.messages import ProposalAdded

        self.assertFalse(mock_publish.called)
        prop = self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalAdded)
        self.assertEqual(prop.pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        mock_publish.reset_mock()
        self.ai.proposals.create()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "publish")
    def test_added_moderator(self, mock_publish):
        from voteit.proposal.messages import ProposalAdded

        self.assertFalse(mock_publish.called)
        prop = self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalAdded)
        self.assertEqual(prop.pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        mock_publish.reset_mock()
        self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalAdded)

    @patch.object(ParticipantsChannel, "publish")
    def test_changed_participant(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        self.prop.body = "Hello"
        self.prop.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(self.prop.pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        mock_publish.reset_mock()
        self.prop.body = "World"
        self.prop.save()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "publish")
    def test_changed_moderator(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        self.prop.body = "Hello"
        self.prop.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(self.prop.pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        mock_publish.reset_mock()
        self.prop.body = "World"
        self.prop.save()
        self.assertTrue(mock_publish.called)

    @patch.object(ParticipantsChannel, "publish")
    def test_deleted_participants(self, mock_publish):
        from voteit.proposal.messages import ProposalDeleted

        self.assertFalse(mock_publish.called)
        prop_pk = self.prop.pk
        self.prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        prop = self.ai.proposals.create()
        mock_publish.reset_mock()
        prop.delete()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "publish")
    def test_deleted_moderators(self, mock_publish):
        from voteit.proposal.messages import ProposalDeleted

        self.assertFalse(mock_publish.called)
        prop_pk = self.prop.pk
        self.prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        prop = self.ai.proposals.create()
        prop_pk = prop.pk
        mock_publish.reset_mock()
        prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.data.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class PrivateAIPublishedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.proposals.create(body="Hello")
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "participant")

    @patch.object(ParticipantsChannel, "publish")
    def test_ai_made_public(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged
        from voteit.proposal.messages import ProposalAdded

        self.ai.upcoming()
        self.ai.save()

        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len([x for x in messages if isinstance(x, AgendaChanged)]))
        self.assertEqual(1, len([x for x in messages if isinstance(x, ProposalAdded)]))


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AgendaItemChannelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem
        from voteit.proposal.models import TextDocument

        cls.meeting: Meeting = Meeting.objects.create(state="upcoming")
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(state="upcoming")
        cls.text_document: TextDocument = cls.ai.text_documents.create(
            body="Hello\n\nWorld", base_tag="hi"
        )
        # cls.para = cls.ai.text_paragraphs.create()
        cls.user = cls.meeting.participants.create(username="participant")
        cls.meeting.add_roles(cls.user, "participant")

    @patch.object(AgendaItemChannel, "publish")
    def test_create(self, mock_publish):
        from voteit.proposal.messages import TextDocumentAdded

        text_doc = self.ai.text_documents.create(
            body="Hello again\n\nWorld", base_tag="world"
        )
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(
            1, len([x for x in messages if isinstance(x, TextDocumentAdded)])
        )
        msg = messages[0]
        self.assertEqual(text_doc.pk, msg.data.pk)
        self.assertEqual(
            ["Hello again", "World"], [x["body"] for x in msg.data.paragraphs]
        )

    @patch.object(AgendaItemChannel, "publish")
    def test_delete(self, mock_publish):
        from voteit.proposal.messages import TextDocumentDeleted

        deleted_pk = self.text_document.pk
        self.text_document.delete()
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(
            1, len([x for x in messages if isinstance(x, TextDocumentDeleted)])
        )
        msg = messages[0]
        self.assertEqual(deleted_pk, msg.data.pk)

    @patch.object(AgendaItemChannel, "publish")
    def test_update(self, mock_publish):
        from voteit.proposal.messages import TextDocumentChanged

        self.text_document.body = "Blaha"
        self.text_document.save()
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(
            1, len([x for x in messages if isinstance(x, TextDocumentChanged)])
        )
        msg = messages[0]
        self.assertEqual(self.text_document.pk, msg.data.pk)
        self.assertEqual("Blaha", msg.data.body)

    def test_subscribe_fetches_text_doc(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.ai.pk,
            channel_type="agenda_item",
        )
        msg = command.run_job()
        pks = set(
            [x.p["pk"] for x in msg.data.app_state if x.t == "text_document.added"]
        )
        self.assertEqual({self.text_document.pk}, pks)
