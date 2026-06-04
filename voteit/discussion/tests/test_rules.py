from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core import PERM
from voteit.discussion.models import DiscussionPost
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER


class RulesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.meeting = Meeting.objects.get(pk=1)
        cls.anon_user = User.objects.create(username="anon")
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.discusser = cls.meeting.participants.create(username="discusser")
        cls.discusser_author = cls.meeting.participants.create(
            username="discusser_author"
        )
        cls.meeting.add_roles(cls.discusser, ROLE_DISCUSSER)
        cls.meeting.add_roles(cls.discusser_author, ROLE_DISCUSSER)
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai.state = "upcoming"
        cls.ai.save()
        cls.discussion_post = cls.ai.discussions.create(author=cls.discusser_author)

    def setUp(self):
        self.meeting.refresh_from_db()
        self.ai.refresh_from_db()

    def p(self, perm):
        return DiscussionPost.get_perm(perm)

    def _archive(self):
        self.meeting.archive()
        self.meeting.save()
        self.ai.refresh_from_db()

    def test_add(self):
        ADD = self.p(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))
        self.assertTrue(self.discusser.has_perm(ADD, self.ai))

    def test_add_with_block(self):
        self.ai.block_discussion = True
        self.ai.save()
        ADD = self.p(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.discusser.has_perm(ADD, self.ai))

    def test_add_archived_meeting(self):
        self._archive()
        ADD = self.p(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.discusser.has_perm(ADD, self.ai))

    def test_change(self):
        CHANGE = self.p(PERM.CHANGE)
        # Maybe we want to allow changes for authors later on...
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.discussion_post))
        self.assertFalse(self.participant.has_perm(CHANGE, self.discussion_post))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.discussion_post))
        self.assertFalse(self.discusser.has_perm(CHANGE, self.discussion_post))
        self.assertFalse(self.discusser_author.has_perm(CHANGE, self.discussion_post))

    def test_change_archived_meeting(self):
        self._archive()
        CHANGE = self.p(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.discussion_post))
        self.assertFalse(self.participant.has_perm(CHANGE, self.discussion_post))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.discussion_post))
        self.assertFalse(self.discusser.has_perm(CHANGE, self.discussion_post))
        self.assertFalse(self.discusser_author.has_perm(CHANGE, self.discussion_post))

    def test_delete(self):
        DELETE = self.p(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.discussion_post))
        self.assertFalse(self.participant.has_perm(DELETE, self.discussion_post))
        self.assertTrue(self.moderator.has_perm(DELETE, self.discussion_post))
        self.assertFalse(self.discusser.has_perm(DELETE, self.discussion_post))
        self.assertTrue(self.discusser_author.has_perm(DELETE, self.discussion_post))

    def test_delete_archived_meeting(self):
        self._archive()
        DELETE = self.p(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.discussion_post))
        self.assertFalse(self.participant.has_perm(DELETE, self.discussion_post))
        self.assertFalse(self.moderator.has_perm(DELETE, self.discussion_post))
        self.assertFalse(self.discusser.has_perm(DELETE, self.discussion_post))
        self.assertFalse(self.discusser_author.has_perm(DELETE, self.discussion_post))
