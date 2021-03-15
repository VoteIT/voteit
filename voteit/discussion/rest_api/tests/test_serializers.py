from datetime import datetime

from django.test import RequestFactory
from django.test import TestCase

from voteit.core.testing import mk_hashtag


class DiscussionPostDetailSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.user = self.meeting.participants.create(username="jane")
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        tag_html = mk_hashtag("world")
        self.disc = self.ai.discussions.create(
            author=self.user, body=f"Hello {tag_html}"
        )

    @property
    def _cut(self):
        from voteit.discussion.rest_api.serializers import (
            DiscussionPostDetailSerializer,
        )

        return DiscussionPostDetailSerializer

    def test_get(self):
        serializer = self._cut(self.disc)
        data = serializer.data
        self.assertEqual(data.pop("pk"), self.disc.pk)
        self.assertIn("Hello", data.pop("body"))
        self.assertEqual(data.pop("agenda_item"), self.ai.pk)
        dt = datetime.strptime(data.pop("created"), "%Y-%m-%dT%H:%M:%S.%f%z")
        self.assertIsInstance(dt, datetime)
        self.assertEqual(data.pop("author"), self.user.pk)
        self.assertEqual(data.pop("tags"), ["world"])
        # Make sure we checked everything
        self.assertFalse(data.keys())

    def test_patch(self):
        serializer = self._cut(self.disc, {"body": "Bye!"}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.disc.body, "Bye!")
        self.assertEqual(self.disc.tags, [])


class DiscussionPostCreateSerializer(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.user = self.meeting.participants.create(username="jane")
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")

    @property
    def _cut(self):
        from voteit.discussion.rest_api.serializers import (
            DiscussionPostCreateSerializer,
        )

        return DiscussionPostCreateSerializer

    def test_create(self):
        rf = RequestFactory()
        request = rf.request()
        request.user = self.user
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
        }
        serializer = self._cut(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        self.assertEqual(["world"], instance.tags)
        self.assertEqual(self.ai, instance.agenda_item)
        self.assertEqual(self.user, instance.author)
