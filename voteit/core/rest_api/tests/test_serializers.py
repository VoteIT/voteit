from django.contrib.auth import get_user_model
from rest_framework.serializers import ModelSerializer
from rest_framework.serializers import Serializer
from voteit.core.testing import mk_usertag, mk_hashtag
from django.test import TestCase


class RichTextSerializerMixinTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Testing abstract model through meeting model
        from voteit.meeting.models import Meeting

        cls.Meeting = Meeting

        cls.meeting = cls.Meeting.objects.create()
        cls.user = cls.meeting.participants.create(username="ivan")
        cls.other_user = cls.meeting.participants.create(username="other")

    def setUp(self):
        self.meeting.refresh_from_db()

    @property
    def _cut(self):
        from voteit.core.rest_api.serializers import RichTextSerializerMixin

        class _Serializer(RichTextSerializerMixin, ModelSerializer):
            class Meta:
                model = self.Meeting
                fields = ["body", "mentions", "tags"]

        return _Serializer

    def test_body_mentions_update(self):
        self.assertFalse(self.meeting.mentions.filter(pk=self.user.pk).exists())
        body = f"Hello {mk_usertag(self.user.pk)} what's up?"
        serializer = self._cut(self.meeting, data={"body": body})
        serializer.is_valid(raise_exception=False)
        # So we see errors in the failed tests
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertTrue(self.meeting.mentions.filter(pk=self.user.pk).exists())

    def test_body_mentions_with_nonexisting_user(self):
        # Shouldn't kill setting text
        deleted_pk = self.user.pk
        self.user.delete()
        body = f"{mk_usertag(deleted_pk)} doesn't exist"
        serializer = self._cut(self.meeting, data={"body": body})
        serializer.is_valid(raise_exception=False)
        self.assertIn("body", serializer.errors)

    def test_mention_user(self):
        serializer = self._cut(
            self.meeting, data={"body": "", "mentions": [self.user.pk]}
        )
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertTrue(self.meeting.mentions.filter(pk=self.user.pk).exists())

    def test_mention_nonexisting_user(self):
        deleted_pk = self.user.pk
        self.user.delete()
        serializer = self._cut(
            self.meeting, data={"body": "", "mentions": [deleted_pk]}
        )
        serializer.is_valid(raise_exception=False)
        self.assertIn("mentions", serializer.errors)

    def test_body_tags(self):
        body = f"{mk_hashtag('SUP')} all {mk_hashtag('participants')}? {mk_hashtag('KörVi')}!"
        serializer = self._cut(self.meeting, data={"body": body})
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(["körvi", "participants", "sup"], self.meeting.tags)

    def test_body_tags_plus_specified(self):
        body = f"{mk_hashtag('SUP')} all {mk_hashtag('participants')}? {mk_hashtag('KörVi')}!"
        serializer = self._cut(self.meeting, data={"body": body, "tags": ["hello"]})
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(["hello", "körvi", "participants", "sup"], self.meeting.tags)

    def test_patch_body(self):
        self.meeting.tags = ["hello", "world"]
        self.meeting.mentions.add(self.user)
        body = f"{mk_hashtag('KörVi')} eller hur {mk_usertag(self.other_user)}!"
        serializer = self._cut(self.meeting, data={"body": body}, partial=True)
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(["hello", "körvi", "world"], self.meeting.tags)
        self.assertEqual(
            {self.user, self.other_user},
            set(self.meeting.mentions.all()),
        )

    def test_patch_mentions(self):
        self.meeting.body = (
            f"{mk_hashtag('KörVi')} eller hur {mk_usertag(self.other_user)}!"
        )
        self.meeting.mentions.add(self.other_user)
        serializer = self._cut(
            self.meeting, data={"mentions": [self.user.pk]}, partial=True
        )
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual({self.user, self.other_user}, set(self.meeting.mentions.all()))

    def test_patch_tags(self):
        self.meeting.body = (
            f"{mk_hashtag('KörVi')} eller hur {mk_usertag(self.other_user)}!"
        )
        serializer = self._cut(self.meeting, data={"tags": ["what"]}, partial=True)
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(["körvi", "what"], self.meeting.tags)

    def test_create(self):
        body = f"{mk_hashtag('SUP')} all {mk_hashtag('participants')}? {mk_hashtag('KörVi')}!"
        serializer = self._cut(
            data={"body": body, "tags": ["yeah"], "mentions": [self.user.pk]}
        )
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        instance = serializer.create(serializer.validated_data)
        self.assertEqual(["körvi", "participants", "sup", "yeah"], instance.tags)
        self.assertEqual(
            [self.user.pk], list(instance.mentions.all().values_list("pk", flat=True))
        )
