from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton


class ButtonDetailSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.button: ReactionButton = cls.meeting.reaction_buttons.create(
            title="Thumbs up", color="primary", icon="mdi-thumb-up"
        )

    @property
    def _cut(self):
        from voteit.reactions.rest_api.serializers import ButtonDetailSerializer

        return ButtonDetailSerializer

    def test_get(self):
        serializer = self._cut(self.button)
        data = serializer.data
        self.assertEqual(
            {
                "pk": self.button.pk,
                "meeting": self.meeting.pk,
                "title": "Thumbs up",
                "color": "primary",
                "icon": "mdi-thumb-up",
                "order": 0,
                "change_roles": [],
                "list_roles": [],
                "active": True,
                "allowed_models": ["proposal", "discussion_post"],
                "target": None,
                "flag_mode": False,
                "on_presentation": False,
                "on_vote": False,
            },
            data,
        )

    def test_patch(self):
        serializer = self._cut(
            self.button, {"title": "Just thumbs", "target": 10}, partial=True
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.button.title, "Just thumbs")
        self.assertEqual(self.button.target, 10)

    def test_patch_bad_roles(self):
        serializer = self._cut(self.button, {"list_roles": ["hello"]}, partial=True)
        serializer.is_valid()
        self.assertIn("list_roles", serializer.errors)

    def test_patch_bad_role_data(self):
        serializer = self._cut(self.button, {"list_roles": "hello"}, partial=True)
        serializer.is_valid()
        self.assertIn("list_roles", serializer.errors)


class ButtonCreateSerializerTests(TestCase):
    def setUp(self):
        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )

    @property
    def _cut(self):
        from voteit.reactions.rest_api.serializers import ButtonCreateSerializer

        return ButtonCreateSerializer

    def test_create(self):
        serializer = self._cut(
            data={
                "meeting": self.meeting.pk,
                "title": "Hello",
                "color": "primary",
                "icon": "mdi-thumb-up",
            }
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, ReactionButton)
        self.assertEqual(instance.meeting, self.meeting)


class ReactionSerializerSerializerTests(TestCase):
    def setUp(self):
        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.ai = self.meeting.agenda_items.create()
        self.prop = self.ai.proposals.create()
        self.user = self.meeting.participants.create(username="Jane")
        self.button: ReactionButton = self.meeting.reaction_buttons.create(
            title="Thumbs up", color="primary", icon="mdi-thumb-up"
        )
        self.reaction: Reaction = self.button.reactions.create(
            user=self.user, object=self.prop
        )

    @property
    def _cut(self):
        from voteit.reactions.rest_api.serializers import ReactionSerializer

        return ReactionSerializer

    def test_get(self):
        serializer = self._cut(self.reaction)
        data = serializer.data
        self.assertEqual(
            {
                "pk": self.reaction.pk,
                "button": self.button.pk,
                "user": self.user.pk,
                "content_type": "proposal",
                "object_id": self.prop.pk,
                "agenda_item": None,
            },
            data,
        )
