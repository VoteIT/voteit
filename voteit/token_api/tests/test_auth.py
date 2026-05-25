from datetime import timedelta

from django.test import RequestFactory
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from voteit.organisation.models import Organisation
from voteit.token_api.auth import MeetingAPIKeyAuthentication
from voteit.token_api.auth import MeetingAPIKeyScope
from voteit.token_api.models import MeetingAPIKey
from voteit.token_api.models import create_api_key_user


class MeetingAPIKeyAuthenticationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.meeting = cls.org.meetings.create(title="Test meeting")
        cls.api_user = create_api_key_user(cls.meeting)
        cls.obj, cls.raw_key = MeetingAPIKey.objects.create_key(
            name="Test key",
            scopes=[],
            meeting=cls.meeting,
            user=cls.api_user,
        )

    def _make_request(self, key):
        request = RequestFactory().get("/")
        request.META["HTTP_AUTHORIZATION"] = f"Api-Key {key}"
        return request

    def _authenticate(self, key):
        return MeetingAPIKeyAuthentication().authenticate(self._make_request(key))

    def test_valid_key_returns_api_key_user(self):
        user, token = self._authenticate(self.raw_key)
        self.assertEqual(user, self.api_user)
        self.assertIsNone(token)

    def test_valid_key_sets_meeting_api_key_on_request(self):
        request = self._make_request(self.raw_key)
        MeetingAPIKeyAuthentication().authenticate(request)
        self.assertEqual(request.meeting_api_key, self.obj)

    def test_valid_key_user_is_inactive(self):
        user, _ = self._authenticate(self.raw_key)
        self.assertFalse(user.is_active)
        self.assertTrue(user.username.startswith("apikey-"))

    def test_invalid_key_raises_authentication_failed(self):
        with self.assertRaises(AuthenticationFailed):
            self._authenticate("invalid.key")

    def test_no_key_returns_none(self):
        request = RequestFactory().get("/")
        result = MeetingAPIKeyAuthentication().authenticate(request)
        self.assertIsNone(result)

    def test_authenticate_prefetches_related_objects(self):
        request = self._make_request(self.raw_key)
        MeetingAPIKeyAuthentication().authenticate(request)
        api_key = request.meeting_api_key
        with self.assertNumQueries(0):
            _ = api_key.user
            _ = api_key.meeting
            _ = api_key.meeting.organisation

    def test_expired_key_raises_authentication_failed(self):
        self.obj.expiry_date = timezone.now() - timedelta(hours=1)
        self.obj.save(update_fields=["expiry_date"])
        with self.assertRaises(AuthenticationFailed):
            self._authenticate(self.raw_key)


class MeetingAPIKeyScopeObjectPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.meeting = cls.org.meetings.create(title="Test meeting")
        cls.other_meeting = cls.org.meetings.create(title="Other meeting")
        cls.api_user = create_api_key_user(cls.meeting)
        cls.obj, cls.raw_key = MeetingAPIKey.objects.create_key(
            name="Test key",
            scopes=["invites.*"],
            meeting=cls.meeting,
            user=cls.api_user,
        )

    def _make_request(self, key=None):
        request = RequestFactory().get("/")
        if key:
            request.META["HTTP_AUTHORIZATION"] = f"Api-Key {key}"
            MeetingAPIKeyAuthentication().authenticate(request)
        return request

    def test_object_in_same_meeting_is_allowed(self):
        request = self._make_request(self.raw_key)
        obj = self.meeting.invites.create(user_data={}, roles=[])
        self.assertTrue(MeetingAPIKeyScope().has_object_permission(request, None, obj))

    def test_object_in_other_meeting_is_denied(self):
        request = self._make_request(self.raw_key)
        obj = self.other_meeting.invites.create(user_data={}, roles=[])
        self.assertFalse(MeetingAPIKeyScope().has_object_permission(request, None, obj))

    def test_session_user_without_api_key_is_denied(self):
        request = self._make_request()
        obj = self.meeting.invites.create(user_data={}, roles=[])
        self.assertFalse(MeetingAPIKeyScope().has_object_permission(request, None, obj))
