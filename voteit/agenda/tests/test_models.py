from datetime import UTC
from datetime import datetime
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.meeting.channels import ModeratorsChannel


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AgendaItemTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create(title="Hello world")

    @property
    def AgendaItem(self):
        from voteit.agenda.models import AgendaItem

        return AgendaItem

    def test_meeting_relation(self):
        obj = self.meeting.agenda_items.create()
        self.assertEqual(obj.meeting, self.meeting)
        self.assertEqual(obj, self.meeting.agenda_items.all()[0])
        self.meeting.delete()
        self.assertEqual(0, self.AgendaItem.objects.count())

    def test_get_discussions(self):
        from voteit.discussion.models import DiscussionPost

        ai = self.meeting.agenda_items.create()
        post = DiscussionPost.objects.create(agenda_item=ai)
        post2 = DiscussionPost.objects.create()
        self.assertIn(post, ai.get_discussions())
        self.assertNotIn(post2, ai.get_discussions())

    def test_get_proposals(self):
        from voteit.proposal.models import Proposal

        ai = self.meeting.agenda_items.create()
        prop = Proposal.objects.create(agenda_item=ai)
        prop2 = Proposal.objects.create()
        self.assertIn(prop, ai.get_proposals())
        self.assertNotIn(prop2, ai.get_proposals())

    def _related_modified(self, ai):
        return (
            self.AgendaItem.objects.with_related_modified()
            .get(pk=ai.pk)
            .related_modified
        )

    def test_related_modified(self):
        ai = self.meeting.agenda_items.create()
        other_ai = self.meeting.agenda_items.create()
        self.assertIsNone(self._related_modified(ai))
        prop = ai.proposals.create(created=datetime(2021, 5, 12, 8, 0, tzinfo=UTC))
        self.assertEqual(prop.created, self._related_modified(ai))
        disc = ai.discussions.create(created=datetime(2021, 5, 12, 12, 0, tzinfo=UTC))
        self.assertEqual(disc.created, self._related_modified(ai))
        # Newer content elsewhere doesn't matter
        other_ai.proposals.create()
        self.assertEqual(disc.created, self._related_modified(ai))
        # Edits don't count as new
        prop.body = "Changed"
        prop.save()
        self.assertEqual(disc.created, self._related_modified(ai))
        disc.delete()
        self.assertEqual(prop.created, self._related_modified(ai))
        prop.delete()
        self.assertIsNone(self._related_modified(ai))

    def test_related_modified_diff_proposal(self):
        from voteit.proposal.models import DiffProposal

        ai = self.meeting.agenda_items.create()
        doc = ai.text_documents.create(body="Hello\n\nworld")
        prop = DiffProposal.objects.create(
            agenda_item=ai, paragraph=doc.text_paragraphs.first()
        )
        self.assertEqual(prop.created, self._related_modified(ai))

    def test_get_related_modified(self):
        ai = self.meeting.agenda_items.create()
        prop = ai.proposals.create()
        with self.assertNumQueries(1):
            self.assertEqual(prop.created, ai.get_related_modified())
        annotated = self.AgendaItem.objects.with_related_modified().get(pk=ai.pk)
        with self.assertNumQueries(0):
            self.assertEqual(prop.created, annotated.get_related_modified())
        self.assertIsNone(self.AgendaItem().get_related_modified())

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_one_push_when_several_proposals_created(self, mock_channel):
        ai = self.meeting.agenda_items.create()
        mock_channel.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            ai.proposals.create()
            ai.proposals.create()
        messages = [x.args[0] for x in mock_channel.mock_calls]
        agenda_messages = [x for x in messages if x.action == "agenda_item.changed"]
        self.assertEqual(1, len(agenda_messages))
        self.assertIsNotNone(agenda_messages[0].payload.related_modified)


class LastReadTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting = meeting = Meeting.objects.first()
        cls.ai = meeting.agenda_items.first()
        cls.user = meeting.participants.first()

    def test_unique_constraint(self):
        self.user.last_read_set.create(meeting=self.meeting, agenda_item=self.ai)
        self.assertEqual(
            self.user.last_read_set.count(), 1, "There should be one last read now"
        )
        with self.assertRaises(IntegrityError):
            self.user.last_read_set.create(meeting=self.meeting, agenda_item=self.ai)
