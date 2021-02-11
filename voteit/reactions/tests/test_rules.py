from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.test import TestCase

from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()


class ModelsTestCase(TestCase):
    def setUp(self):
        from voteit.discussion.models import DiscussionPost
        from voteit.meeting.models import Meeting
        from voteit.proposal.models import Proposal
        from voteit.reactions.models import ReactionButton

        self.meeting = Meeting.objects.create(title="Test meeting")
        self.prop1: Proposal = Proposal.objects.create()
        self.prop2 = Proposal.objects.create()
        self.post1 = DiscussionPost.objects.create()
        self.like_button = ReactionButton.objects.create(
            title="Like", icon="thumb_up", color="success", meeting=self.meeting
        )
        self.dislike_button = ReactionButton.objects.create(
            title="Dislike", icon="thumb_up", color="danger", meeting=self.meeting
        )
        self.accessible_button = ReactionButton.objects.create(
            title="Accessible", icon="accessible", color="primary", meeting=self.meeting
        )
        content_types = ContentType.objects.get_for_models(Proposal, DiscussionPost)
        # self.like_button.role_set.create(
        #     content_type=content_types[Proposal], change=True, role=ROLE_PARTICIPANT
        # )
        # self.dislike_button.role_set.create(
        #     content_type=content_types[Proposal], change=True, role=ROLE_PARTICIPANT
        # )
        # for ct in content_types.values():
        #     self.accessible_button.role_set.create(
        #         content_type=ct, change=True, role=ROLE_PARTICIPANT
        #     )
        self.user1 = User.objects.create_user("user1")
        self.user2 = User.objects.create_user("user2")
        # Make users participants
        self.meeting.add_roles(self.user1, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.user2, ROLE_PARTICIPANT)

    # def test_role_set(self):
    #     with self.assertRaises(ValueError):
    #         next(self.like_button.get_valid_roles(None, "bad_mode"))
    #     self.assertEqual(self.like_button.role_set.count(), 1)
    #     self.assertEqual(self.accessible_button.role_set.count(), 2)
    #     self.assertIs(self.like_button.role_set.first().role, ROLE_PARTICIPANT)

    def test_unique(self):
        from django.db import IntegrityError

        self.prop1.reaction_set.create(user=self.user1, button=self.like_button)
        self.prop2.reaction_set.create(user=self.user1, button=self.like_button)
        self.prop1.reaction_set.create(user=self.user2, button=self.like_button)
        self.assertRaises(
            IntegrityError,
            self.prop1.reaction_set.create,
            user=self.user1,
            button=self.like_button,
        )

    def test_order(self):
        self.assertEqual(self.like_button.order, 0)
        self.assertEqual(self.dislike_button.order, 1)
        self.assertEqual(self.accessible_button.order, 2)

    def test_count(self):
        self.prop1.reaction_set.create(user=self.user1, button=self.like_button)
        self.prop1.reaction_set.create(user=self.user2, button=self.like_button)
        self.prop1.reaction_set.create(user=self.user1, button=self.dislike_button)
        qs = self.meeting.reactionbutton_set.counts_for_object(self.prop1).order_by(
            "title"
        )
        self.assertEqual(qs.count(), 3)
        self.assertEqual(qs[0].title, "Accessible")
        self.assertEqual(qs[0].count, 0)
        self.assertEqual(qs[1].title, "Dislike")
        self.assertEqual(qs[1].count, 1)
        self.assertEqual(qs[2].title, "Like")
        self.assertEqual(qs[2].count, 2)

    # def test_discussion(self):
    #     self.post1.reaction_set.create(user=self.user1, button=self.accessible_button)
    #     self.assertRaises(
    #         IntegrityError,
    #         self.post1.reaction_set.create,
    #         user=self.user1,
    #         button=self.like_button,
    #     )
