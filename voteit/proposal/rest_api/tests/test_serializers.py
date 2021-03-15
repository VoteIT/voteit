from datetime import datetime

from django.test import RequestFactory
from django.test import TestCase

from voteit.core.testing import mk_hashtag


class ProposalDetailSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.user = self.meeting.participants.create(username="jane")
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        tag_html = mk_hashtag("world")
        self.prop = self.ai.proposals.create(author=self.user, body=f"Hello {tag_html}")

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import ProposalDetailSerializer

        return ProposalDetailSerializer

    def test_get(self):
        serializer = self._cut(self.prop)
        data = serializer.data
        self.assertEqual(data.pop("pk"), self.prop.pk)
        self.assertIn("Hello", data.pop("body"))
        self.assertEqual(data.pop("agenda_item"), self.ai.pk)
        dt = datetime.strptime(data.pop("created"), "%Y-%m-%dT%H:%M:%S.%f%z")
        self.assertIsInstance(dt, datetime)
        self.assertEqual(data.pop("author"), self.user.pk)
        prop_id = data.pop("prop_id")
        tags = data.pop("tags")
        self.assertIn(prop_id, tags)
        self.assertIn("world", tags)
        self.assertEqual(2, len(tags))
        self.assertIsInstance(prop_id, str)
        self.assertEqual("published", data.pop("state"))
        # Make sure we checked everything
        self.assertFalse(data.keys())

    def test_patch(self):
        serializer = self._cut(self.prop, {"body": "Bye!"}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.prop.body, "Bye!")
        self.assertEqual(1, len(self.prop.tags))  # prop_id


class ProposalCreateSerializer(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.user = self.meeting.participants.create(username="jane")
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import ProposalCreateSerializer

        return ProposalCreateSerializer

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
        self.assertIn("world", instance.tags)
        self.assertIn(instance.prop_id, instance.tags)
        self.assertEqual(self.ai, instance.agenda_item)
        self.assertEqual(self.user, instance.author)
