from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from rest_framework.serializers import ModelSerializer

from voteit.agenda.models import AgendaItem
from voteit.core.testing import mk_hashtag
from voteit.core.testing import mk_usertag
from voteit.meeting.models import Meeting
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import Organisation

User = get_user_model()

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


class RichTextSerializerMixinTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Testing abstract model through agenda item model
        from voteit.core.rest_api.serializers import RichTextSerializerMixin

        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.user = cls.meeting.participants.create(username="ivan")
        cls.other_user = cls.meeting.participants.create(username="other")
        cls.outsider = User.objects.create(username="outsider")

        class _Serializer(RichTextSerializerMixin, ModelSerializer):
            class Meta:
                model = AgendaItem
                fields = ["body", "mentions", "tags", "meeting"]

        cls.Serializer = _Serializer

    def setUp(self):
        self.ai.refresh_from_db()

    def test_body_mentions_update(self):
        self.assertFalse(self.ai.mentions.filter(pk=self.user.pk).exists())
        body = f"Hello {mk_usertag(self.user.pk)} what's up?"
        serializer = self.Serializer(self.ai, data={"body": body}, partial=True)
        serializer.is_valid(raise_exception=False)
        # So we see errors in the failed tests
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertTrue(self.ai.mentions.filter(pk=self.user.pk).exists())

    def test_body_mentions_dont_fetch_update(self):
        self.assertFalse(self.ai.mentions.filter(pk=self.user.pk).exists())
        body = f"Hello {mk_usertag(self.user.pk)} what's up?"
        serializer = self.Serializer(self.ai, data={"body": body}, partial=True)
        serializer.add_body_mentions = False
        serializer.is_valid(raise_exception=False)
        # So we see errors in the failed tests
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertFalse(self.ai.mentions.filter(pk=self.user.pk).exists())

    def test_body_mentions_with_nonexisting_user(self):
        # Shouldn't kill setting text
        deleted_pk = self.user.pk
        self.user.delete()
        body = f"{mk_usertag(deleted_pk)} doesn't exist"
        serializer = self.Serializer(self.ai, data={"body": body}, partial=True)
        serializer.is_valid(raise_exception=False)
        self.assertIn("body", serializer.errors)

    def test_mention_user(self):
        serializer = self.Serializer(
            self.ai, data={"body": "", "mentions": [self.user.pk]}, partial=True
        )
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertTrue(self.ai.mentions.filter(pk=self.user.pk).exists())

    def test_mention_nonexisting_user(self):
        deleted_pk = self.user.pk
        self.user.delete()
        serializer = self.Serializer(
            self.ai, data={"body": "", "mentions": [deleted_pk]}, partial=True
        )
        serializer.is_valid(raise_exception=False)
        self.assertIn("mentions", serializer.errors)

    def test_body_tags(self):
        body = f"{mk_hashtag('SUP')} all {mk_hashtag('participants')}? {mk_hashtag('KörVi')}!"
        serializer = self.Serializer(self.ai, data={"body": body}, partial=True)
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(["körvi", "participants", "sup"], self.ai.tags)

    def test_bad_body_tags(self):
        body = f"{mk_hashtag('S!P')}"
        serializer = self.Serializer(self.ai, data={"body": body}, partial=True)
        serializer.is_valid(raise_exception=False)
        self.assertIn("body", serializer.errors)

    def test_bad_tag_update(self):
        serializer = self.Serializer(
            self.ai, data={"tags": [" w e ", "are"]}, partial=True
        )
        serializer.is_valid()
        self.assertIn("tags", serializer.errors)

    def test_dont_add_body_tags(self):
        body = f"{mk_hashtag('SUP')} all {mk_hashtag('participants')}? {mk_hashtag('KörVi')}!"
        serializer = self.Serializer(self.ai, data={"body": body}, partial=True)
        serializer.add_body_tags = False
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual([], self.ai.tags)

    def test_body_tags_plus_specified(self):
        body = f"{mk_hashtag('SUP')} all {mk_hashtag('participants')}? {mk_hashtag('KörVi')}!"
        serializer = self.Serializer(
            self.ai, data={"body": body, "tags": ["hello"]}, partial=True
        )
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(["hello", "körvi", "participants", "sup"], self.ai.tags)

    def test_patch_body(self):
        self.ai.tags = ["hello", "world"]
        self.ai.mentions.add(self.user)
        body = f"{mk_hashtag('KörVi')} eller hur {mk_usertag(self.other_user)}!"
        serializer = self.Serializer(self.ai, data={"body": body}, partial=True)
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(["hello", "körvi", "world"], self.ai.tags)
        self.assertEqual(
            {self.user, self.other_user},
            set(self.ai.mentions.all()),
        )

    def test_patch_mentions(self):
        self.ai.body = f"{mk_hashtag('KörVi')} eller hur {mk_usertag(self.other_user)}!"
        self.ai.mentions.add(self.other_user)
        serializer = self.Serializer(
            self.ai, data={"mentions": [self.user.pk]}, partial=True
        )
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual({self.user, self.other_user}, set(self.ai.mentions.all()))

    def test_patch_tags(self):
        self.ai.body = f"{mk_hashtag('KörVi')} eller hur {mk_usertag(self.other_user)}!"
        serializer = self.Serializer(self.ai, data={"tags": ["what"]}, partial=True)
        serializer.is_valid(raise_exception=False)
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(["körvi", "what"], self.ai.tags)

    def test_create(self):
        body = f"{mk_hashtag('SUP')} all {mk_hashtag('participants')}? {mk_hashtag('KörVi')}!"
        serializer = self.Serializer(
            data={
                "body": body,
                "tags": ["yeah"],
                "mentions": [self.user.pk],
                "meeting": self.meeting.pk,
            }
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
        cls.user: UserType = User.objects.get(pk=1)
        cls.user.identity_id = "abc"
        cls.user.save()
        cls.user.social_auth.create(
            uid=cls.user.identity_id,
            provider=IDPROXY_PROVIDER,
            extra_data={"user_data": {"email": ["hello@betahaus.net"]}},
        )

    @property
    def _cut(self):
        from voteit.core.rest_api.serializers import UserSerializer

        return UserSerializer

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

    def test_update_userid_same_as_other_org(self):
        other_org = Organisation.objects.create()
        other_org.users.create(username="other", userid="other")
        serializer = self._mk_serializer({"userid": "other"})
        self.assertFalse(serializer.errors)

    def test_update_names(self):
        serializer = self._mk_serializer({"first_name": "Hello", "last_name": "World"})
        serializer.save()
        self.assertEqual("Hello", self.user.first_name)
        self.assertEqual("World", self.user.last_name)
