from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import build_app_state

from voteit.messaging.state import AppState

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.proposal.models import TextDocument
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer

if TYPE_CHECKING:
    from voteit.proposal.models import DiffProposal


User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingSubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai.state = "upcoming"
        cls.ai.save()
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_MODERATOR)

    def setUp(self):
        self.ai.refresh_from_db()

    def test_app_state_sent_moderators(self):
        app_state = build_app_state("moderators", self.meeting.pk, self.user.pk)
        pks = set()
        for msg in app_state:
            if msg.action == "proposal.changed.batch":
                pks = {x.pk for x in msg.payload.items}
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_app_state_sent_private_moderators(self):
        self.ai.state = "private"
        self.ai.save()
        app_state = build_app_state("moderators", self.meeting.pk, self.user.pk)
        pks = set()
        for msg in app_state:
            if msg.action == "proposal.changed.batch":
                pks = {x.pk for x in msg.payload.items}
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_date_of_proposals_on_subscribe(self):
        app_state = build_app_state("moderators", self.meeting.pk, self.user.pk)
        for msg in app_state:
            if msg.action == "proposal.changed.batch":
                break
        first = msg.payload.items[0]
        self.assertIsInstance(first.created, str)
        self.assertEqual(
            ProposalDetailSerializer(self.prop1).data["created"], first.created
        )

    def test_app_state_sent_participants(self):
        app_state = build_app_state("participants", self.meeting.pk, self.user.pk)
        pks = set()
        for msg in app_state:
            if msg.action == "proposal.changed.batch":
                pks = {x.pk for x in msg.payload.items}
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_app_state_sent_private_participants(self):
        self.ai.state = "private"
        self.ai.save()
        app_state = build_app_state("participants", self.meeting.pk, self.user.pk)
        pks = set()
        for msg in app_state:
            if msg.action == "proposal.changed.batch":
                pks = {x.pk for x in msg.payload.items}
        self.assertEqual(set(), pks)

    def test_attach_proposals_query_count(self):
        from voteit.proposal.signals import attach_proposals

        self.prop1.mentions.add(self.user)
        app_state = AppState()
        with self.assertNumQueries(3):
            attach_proposals(self.meeting, app_state, include_private=False)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AnyProposalChangedTests(TestCase):
    """
    Must catch other types too
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai.state = "upcoming"
        cls.ai.save()
        cls.text_doc: TextDocument = cls.ai.text_documents.create(
            body="Hello", base_tag="hi"
        )
        cls.para = cls.text_doc.text_paragraphs.first()
        cls.prop = cls.ai.proposals.create()
        cls.diff_prop: DiffProposal = cls.para.proposals.create(
            agenda_item=cls.ai,  # paragraph=cls.para
        )

    def _mk_diff_prop(self) -> DiffProposal:
        return self.para.proposals.create(
            agenda_item=self.ai,  # paragraph=cls.para
        )

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_added_participant(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        prop = self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(prop.pk, msg.payload.pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_added_in_private_ai_participant(self, mock_publish):
        self.assertFalse(mock_publish.called)
        self.ai.state = "private"
        self.ai.save()
        mock_publish.reset_mock()
        self.ai.proposals.create()
        self.assertFalse(mock_publish.called)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_diff_proposal_added(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        diff_prop = self._mk_diff_prop()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(diff_prop.pk, msg.payload.pk)
        self.assertEqual(msg.payload.paragraph, diff_prop.paragraph.pk)

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_added_moderator(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        prop = self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(prop.pk, msg.payload.pk)
        self.ai.state = "private"
        self.ai.save()
        mock_publish.reset_mock()
        self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_changed_participant(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        self.prop.body = "Hello"
        self.prop.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(self.prop.pk, msg.payload.pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_diff_changed_participant(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        self.diff_prop.body = "Hello"
        self.diff_prop.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(self.diff_prop.pk, msg.payload.pk)
        self.assertEqual(self.diff_prop.paragraph.pk, msg.payload.paragraph)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_changed_private_ai_participant(self, mock_publish):
        self.ai.state = "private"
        self.ai.save()
        mock_publish.reset_mock()
        self.assertFalse(mock_publish.called)
        self.prop.body = "Hello"
        self.prop.save()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_changed_moderator(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        self.prop.body = "Hello"
        self.prop.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(self.prop.pk, msg.payload.pk)
        self.ai.state = "private"
        self.ai.save()
        mock_publish.reset_mock()
        self.prop.body = "World"
        self.prop.save()
        self.assertTrue(mock_publish.called)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_deleted_participants(self, mock_publish):
        from voteit.proposal.messages import ProposalDeleted

        self.assertFalse(mock_publish.called)
        prop_pk = self.prop.pk
        self.prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.payload.pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_deleted_diff_participants(self, mock_publish):
        from voteit.proposal.messages import ProposalDeleted

        self.assertFalse(mock_publish.called)
        diff_prop_pk = self.diff_prop.pk
        self.diff_prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(diff_prop_pk, msg.payload.pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_deleted_participants_private_ai(self, mock_publish):
        self.ai.state = "private"
        self.ai.save()
        mock_publish.reset_mock()
        self.assertFalse(mock_publish.called)
        self.prop.delete()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_deleted_moderators(self, mock_publish):
        from voteit.proposal.messages import ProposalDeleted

        self.assertFalse(mock_publish.called)
        prop_pk = self.prop.pk
        self.prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.payload.pk)
        self.ai.state = "private"
        self.ai.save()
        prop = self.ai.proposals.create()
        prop_pk = prop.pk
        mock_publish.reset_mock()
        prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.payload.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class PrivateAIPublishedTests(TestCase):
    def setUp(self):
        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.proposals.create(body="Hello")
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, ROLE_PARTICIPANT)
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_ai_made_public(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged
        from voteit.proposal.messages import ProposalChanged

        self.ai.make_upcoming(user=self.moderator)
        self.ai.save()
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len([x for x in messages if isinstance(x, AgendaChanged)]))
        self.assertEqual(
            1, len([x for x in messages if isinstance(x, ProposalChanged)])
        )


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AgendaItemChannelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(state="upcoming")
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(state="upcoming")
        cls.text_document: TextDocument = cls.ai.text_documents.create(
            body="Hello\n\nWorld", base_tag="hi"
        )
        cls.user = cls.meeting.participants.create(username="participant")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT)

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_create(self, mock_publish):
        from voteit.proposal.messages import TextDocumentChanged

        text_doc = self.ai.text_documents.create(
            body="Hello again\n\nWorld", base_tag="world"
        )
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        msg = messages[0]
        self.assertEqual(
            1, len([x for x in messages if isinstance(x, TextDocumentChanged)])
        )
        self.assertEqual(text_doc.pk, msg.payload.pk)
        self.assertEqual(
            ["Hello again", "World"], [x["body"] for x in msg.payload.paragraphs]
        )

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_delete(self, mock_publish):
        from voteit.proposal.messages import TextDocumentDeleted

        deleted_pk = self.text_document.pk
        self.text_document.delete()
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        msg = messages[0]
        self.assertEqual(
            1, len([x for x in messages if isinstance(x, TextDocumentDeleted)])
        )
        self.assertEqual(deleted_pk, msg.payload.pk)

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_update(self, mock_publish):
        from voteit.proposal.messages import TextDocumentChanged

        self.text_document.body = "Blaha"
        self.text_document.save()
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        msg = messages[0]
        self.assertEqual(
            1, len([x for x in messages if isinstance(x, TextDocumentChanged)])
        )
        self.assertEqual(self.text_document.pk, msg.payload.pk)
        self.assertEqual("Blaha", msg.payload.body)

    def test_subscribe_fetches_text_doc(self):
        app_state = build_app_state("agenda_item", self.ai.pk, self.user.pk)
        pks = {x.payload.pk for x in app_state if x.action == "text_document.changed"}
        self.assertEqual({self.text_document.pk}, pks)
