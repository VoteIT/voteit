from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from envelope.testing import testing_channel_layers_setting

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

    def test_related_modified(self):
        ai = self.meeting.agenda_items.create()
        self.assertIsNone(ai.maybe_mark_related_modified())
        ai.related_modified = now() - timedelta(minutes=1)
        ai.save()
        self.assertIsNotNone(ai.maybe_mark_related_modified())

    def test_revert_to_last_related_modified(self):
        ai = self.meeting.agenda_items.create()
        ai.revert_to_last_related_modified()  # Should not trigger error
        prop = ai.proposals.create()
        prop.modified = datetime(2021, 5, 12, 8, 0, tzinfo=UTC)
        prop.save()
        disc = ai.discussions.create()
        disc.modified = datetime(2021, 5, 12, 12, 0, tzinfo=UTC)
        disc.save()
        ai.related_modified = datetime(2021, 1, 1, tzinfo=UTC)
        ai.save()
        ai.revert_to_last_related_modified()
        self.assertEqual(disc.modified, ai.related_modified)
        disc.delete()
        ai.revert_to_last_related_modified()
        self.assertEqual(prop.modified, ai.related_modified)
        prop.delete()
        ai.revert_to_last_related_modified()
        self.assertIsNone(ai.related_modified)

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_only_one_push_when_several_proposals_changed(self, mock_channel):
        ai = self.meeting.agenda_items.create()
        ai.related_modified = now() - timedelta(minutes=1)
        ai.save()
        mock_channel.reset_mock()
        ai.proposals.create()
        ai.proposals.create()
        messages = {x.args[0] for x in mock_channel.mock_calls}
        agenda_messages = [x for x in messages if x.name == "agenda_item.changed"]
        self.assertEqual(1, len(agenda_messages))


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
