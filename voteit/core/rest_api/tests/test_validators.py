from django.test import RequestFactory
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from voteit.core.testing import mk_hashtag
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR


class ValidateGroupAIContextTests(TestCase):
    """
    Tested through DiscussionPostCreateSerializer
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.group = cls.meeting.groups.create(title="Our gang")
        cls.user = cls.meeting.participants.create(username="jane")
        cls.moderator = cls.meeting.participants.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.meeting.add_roles(cls.user, ROLE_DISCUSSER)
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        # Outside of test meeting
        cls.other_meeting: Meeting = Meeting.objects.create(title="Other meeting")
        cls.other_group = cls.other_meeting.groups.create(title="Other")

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

    def test_create_as_group(self):
        self.group.post_as = True
        self.group.save()
        self.group.members.add(self.user)
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.group.pk,
            "as_group": True,
        }
        request = self._mk_request()
        serializer = self._cut(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        self.assertEqual(self.group, instance.meeting_group)
        self.assertTrue(instance.as_group)

    def test_create_as_group_that_doesnt_allow_as(self):
        self.group.members.add(self.user)
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.group.pk,
            "as_group": True,
        }
        request = self._mk_request()
        serializer = self._cut(data=data, context={"request": request})
        with self.assertRaises(ValidationError) as cm:
            serializer.is_valid(raise_exception=True)
        self.assertIn("as_group", cm.exception.detail)
        self.assertEqual(
            "This meeting group doesn't allow you to create posts in its name. (post_as=False)",
            str(cm.exception.detail["as_group"][0]),
        )

    def test_create_unrelated_group(self):
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.group.pk,
        }
        request = self._mk_request()
        serializer = self._cut(data=data, context={"request": request})
        with self.assertRaises(ValidationError) as cm:
            serializer.is_valid(raise_exception=True)
        self.assertIn("meeting_group", cm.exception.detail)
        self.assertEqual(
            "You're not a member of this group",
            str(cm.exception.detail["meeting_group"][0]),
        )

    def test_create_group_from_another_meeting(self):
        # This part should be caught by the requirement on BaseModelSerializer
        self.other_group.members.add(self.user)
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.other_group.pk,
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
