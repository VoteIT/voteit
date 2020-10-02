from django.test import TestCase

# Create your tests here.


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
        ai = self._mk_one()
        poll = Poll.objects.create(agenda_item=ai)
        poll2 = Poll.objects.create()
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

    def test_rich_text(self):
        ai = self._mk_one(
            title='Test',
            description='<script type="text/javascript" src="evil-site"></script><a>Test</a>'
                        '<a href="/somewhere" data-user-id="123">Användarnamn</a>',
        )
        ai.full_clean()
        self.assertIn('<user data-user-id="123"/>', ai.description.db_value)
        self.assertIn('<a data-user-id="123">Unknown user</a>', str(ai.description))

    def test_rich_text_existing_user(self):
        from django.contrib.auth.models import User
        ai = self._mk_one(
            title='Test',
            description='<script type="text/javascript" src="evil-site"></script><a>Test</a>'
                        '<a href="/somewhere" data-user-id="1">Användarnamn</a>',
        )
        User.objects.create_user('admin', first_name='Test', last_name='Admin')
        ai.full_clean()
        self.assertIn('<a data-user-id="1" href="/user-info-url/1">Test Admin</a>', str(ai.description))
