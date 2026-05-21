from django.test import RequestFactory
from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed

from voteit.organisation.models import Organisation
from voteit.token_api.auth import MeetingAPIKeyAuthentication
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
