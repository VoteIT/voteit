from django.test import TestCase


class ButtonDetailSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.reactions.models import ReactionButton

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.button: ReactionButton = self.meeting.reaction_buttons.create(
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
            },
            data,
        )

    def test_patch(self):
        serializer = self._cut(self.button, {"title": "Just thumbs"}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.button.title, "Just thumbs")


class ButtonCreateSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )

    @property
    def _cut(self):
        from voteit.reactions.rest_api.serializers import ButtonCreateSerializer

        return ButtonCreateSerializer

    def test_create(self):
        from voteit.reactions.models import ReactionButton

        serializer = self._cut(
            data={
                "meeting": self.meeting.pk,
                "title": "Hello",
                "color": "primary",
                "icon": "mdi-thumb-up",
            }
        )
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        self.assertIsInstance(instance, ReactionButton)
        self.assertEqual(instance.meeting, self.meeting)


class ReactionSerializerSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.reactions.models import Reaction
        from voteit.reactions.models import ReactionButton

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
