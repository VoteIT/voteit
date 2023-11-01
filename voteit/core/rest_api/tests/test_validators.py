from django.test import RequestFactory
from django.test import TestCase
from voteit.core.testing import mk_hashtag
from voteit.meeting.roles import ROLE_MODERATOR


class ValidateGroupAIContextTests(TestCase):

    """
    Tested through DiscussionPostCreateSerializer
    """

    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.group = self.meeting.groups.create()
        self.user = self.meeting.participants.create(username="jane")
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")

    @property
    def _cut(self):
        from voteit.discussion.rest_api.serializers import (
            DiscussionPostCreateSerializer,
        )

        return DiscussionPostCreateSerializer

    def _mk_request(self):
        rf = RequestFactory()
        request = rf.request()
        request.user = self.user
        return request

    def test_create(self):
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
        }
        request = self._mk_request()
        serializer = self._cut(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid())
        instance = serializer.create(serializer.validated_data)
        self.assertEqual(self.ai, instance.agenda_item)
        self.assertEqual(self.user, instance.author)

    def test_create_with_group(self):
        self.group.members.add(self.user)
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.group.pk,
        }
        request = self._mk_request()
        serializer = self._cut(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid())
        instance = serializer.create(serializer.validated_data)
        self.assertEqual(self.group, instance.meeting_group)

    def test_create_unrelated_group(self):
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.group.pk,
        }
        request = self._mk_request()
        serializer = self._cut(data=data, context={"request": request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("meeting_group", serializer.errors)

    def test_create_unrelated_group_with_moderator(self):
        self.meeting.add_roles(self.user, ROLE_MODERATOR)
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.group.pk,
        }
        request = self._mk_request()
        serializer = self._cut(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid())
        instance = serializer.create(serializer.validated_data)
        self.assertEqual(self.group, instance.meeting_group)
