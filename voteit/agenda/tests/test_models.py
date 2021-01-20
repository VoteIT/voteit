from django.test import TestCase


class AgendaItemTests(TestCase):

    def setUp(self):
        from voteit.meeting.models import Meeting
        self.meeting = Meeting.objects.create(title="Hello world")

    @property
    def AgendaItem(self):
        from voteit.agenda.models import AgendaItem
        return AgendaItem

    def _mk_one(self, **kw):
        kw.setdefault("meeting", self.meeting)
        return self.AgendaItem.objects.create(**kw)

    def test_meeting_relation(self):
        obj = self._mk_one(meeting=self.meeting)
        self.assertEqual(obj.meeting, self.meeting)
        self.assertEqual(obj, self.meeting.agenda_items.all()[0])
        self.meeting.delete()
        self.assertEqual(0, self.AgendaItem.objects.count())

    def test_get_polls(self):
        from voteit.poll.models import Poll
        from voteit.poll.app.polls import Simple
        ai = self._mk_one()
        poll = Poll.objects.create(agenda_item=ai, method=Simple.objects.create())
        poll2 = Poll.objects.create(method=Simple.objects.create())
        self.assertIn(poll, ai.get_polls())
        self.assertNotIn(poll2, ai.get_polls())

    def test_get_discussions(self):
        from voteit.discussion.models import DiscussionPost
        ai = self._mk_one()
        post = DiscussionPost.objects.create(agenda_item=ai)
        post2 = DiscussionPost.objects.create()
        self.assertIn(post, ai.get_discussions())
        self.assertNotIn(post2, ai.get_discussions())

    def test_get_proposals(self):
        from voteit.proposal.models import Proposal
        ai = self._mk_one()
        prop = Proposal.objects.create(agenda_item=ai)
        prop2 = Proposal.objects.create()
        self.assertIn(prop, ai.get_proposals())
        self.assertNotIn(prop2, ai.get_proposals())
