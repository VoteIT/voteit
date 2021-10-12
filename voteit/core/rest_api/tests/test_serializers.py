from datetime import timedelta
from typing import TYPE_CHECKING

import responses
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from django.utils.timezone import now
from rest_framework.serializers import ModelSerializer

from voteit.core.testing import mk_hashtag
from voteit.core.testing import mk_usertag

User = get_user_model()

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


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


class UpdateUserSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import OAuth2Provider

        cls.mock_api_return = {
            "pk": 1,
            "application": 1,
            "given_name": "Hello",
            "family_name": "Is it me you are looking for?",
            "identity_id": "123",
            "user_data": [
                {
                    "pk": 1,
                    "scope": "email",
                    "data": "hello@betahaus.net",
                    "validated": "2021-03-24T15:56:00.043000Z",
                },
                {
                    "pk": 2,
                    "scope": "cell_phone",
                    "data": "+123-123-123",
                    "validated": "2021-03-24T15:56:00.043000Z",
                },
            ],
        }

        cls.provider: OAuth2Provider = OAuth2Provider.objects.get(pk=1)
        cls.user: UserType = User.objects.get(pk=1)
        cls.user.access_tokens.create(
            expires_at=now() + timedelta(hours=1),
            expires_in=3600,
            provider=cls.provider,
            access_token="abc",
            refresh_token="123",
        )

        cls.responses = responses.RequestsMock()
        cls.responses.start()
        cls.responses.add(
            responses.GET, cls.provider.identity_url, json=cls.mock_api_return
        )

    def setUp(self):
        self.user.refresh_from_db()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.responses.stop()
        cls.responses.reset()

    @property
    def _cut(self):
        from voteit.core.rest_api.serializers import UpdateUserSerializer

        return UpdateUserSerializer

    def _mk_serializer(self, data):
        request = RequestFactory().get("/")
        request.user = self.user
        serializer = self._cut(
            self.user, data=data, partial=True, context={"request": request}
        )
        serializer.is_valid()
        return serializer

    def test_update_email(self):
        serializer = self._mk_serializer({"email": "hello@betahaus.net"})
        self.assertFalse(serializer.errors)

    def test_update_email_not_in_identity_data(self):
        serializer = self._mk_serializer({"email": "idontexist@betahaus.net"})
        self.assertIn("email", serializer.errors)

    def test_update_userid(self):
        serializer = self._mk_serializer({"userid": "something_new"})
        self.assertFalse(serializer.errors)

    def test_update_userid_already_exists(self):
        serializer = self._mk_serializer({"userid": "participant"})
        self.assertIn("userid", serializer.errors)

    def test_update_userid_bad_name(self):
        serializer = self._mk_serializer({"userid": "HELLO"})
        self.assertIn("userid", serializer.errors)
