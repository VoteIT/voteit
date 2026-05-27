from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.models import Meeting
from voteit.reactions.models import ReactionButton

User = get_user_model()


class ModelsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(title="Test meeting")
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.post1 = cls.ai.discussions.create()
        cls.like_button: ReactionButton = ReactionButton.objects.create(
            title="Like", icon="thumb_up", color="success", meeting=cls.meeting
        )
        cls.dislike_button: ReactionButton = ReactionButton.objects.create(
            title="Dislike", icon="thumb_down", color="danger", meeting=cls.meeting
        )
        cls.accessible_button: ReactionButton = ReactionButton.objects.create(
            title="Accessible", icon="accessible", color="primary", meeting=cls.meeting
        )
        cls.user1 = User.objects.create_user("user1")
        cls.user2 = User.objects.create_user("user2")
        # Make users participants
        cls.meeting.add_roles(cls.user1, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.user2, ROLE_PARTICIPANT)

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_unique(self):
        self.prop1.reaction_set.create(
            user=self.user1, button=self.like_button, agenda_item=self.ai
        )
        self.prop2.reaction_set.create(
            user=self.user1, button=self.like_button, agenda_item=self.ai
        )
        self.prop1.reaction_set.create(
            user=self.user2, button=self.like_button, agenda_item=self.ai
        )
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
        self.prop1.reaction_set.create(
            user=self.user1, button=self.like_button, agenda_item=self.ai
        )
        self.prop1.reaction_set.create(
            user=self.user2, button=self.like_button, agenda_item=self.ai
        )
        self.prop1.reaction_set.create(
            user=self.user1, button=self.dislike_button, agenda_item=self.ai
        )
        qs = self.meeting.reaction_buttons.counts_for_object(self.prop1).order_by(
            "title"
        )
        self.assertEqual(qs.count(), 3)
        self.assertEqual(qs[0].title, "Accessible")
        self.assertEqual(qs[0].count, 0)
        self.assertEqual(qs[1].title, "Dislike")
        self.assertEqual(qs[1].count, 1)
        self.assertEqual(qs[2].title, "Like")
        self.assertEqual(qs[2].count, 2)

    def test_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.assertTrue(self.meeting.is_archived)
        self.like_button.title = "Me like"
        self.assertRaises(IntegrityError, self.like_button.save)

    def test_invalid_change_roles(self):
        self.like_button.change_roles = ["404"]
        self.assertRaises(ValueError, self.like_button.save)

    def test_invalid_list_roles(self):
        self.like_button.list_roles = ["404"]
        self.assertRaises(ValueError, self.like_button.save)

    def test_uniqueish_buttons_required(self):
        self.dislike_button.title = "like"
        self.dislike_button.save()
        self.dislike_button.color = self.like_button.color.upper()
        self.dislike_button.save()
        self.dislike_button.icon = self.like_button.icon
        with self.assertRaises(IntegrityError):
            self.dislike_button.save()
