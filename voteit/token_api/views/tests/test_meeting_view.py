from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.token_api.models import MeetingAPIKey
from voteit.token_api.models import create_api_key_user
from voteit.organisation.models import Organisation

User = get_user_model()

URL = "token-api:meeting-list"


class MeetingViewTest(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.meeting = cls.org.meetings.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def _create_key(self, scopes):
        api_user = create_api_key_user(self.meeting)
        obj, key = MeetingAPIKey.objects.create_key(
            name="Test key",
            scopes=scopes,
            meeting=self.meeting,
            user=api_user,
        )
        return obj, key

    def _api_key_client(self, key: str):
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")

    # --- unauthenticated ---

    def test_unauthenticated_returns_403(self):
        # Same as revoked key: no WWW-Authenticate header → DRF returns 403.
        response = self.client.get(reverse(URL))
        self.assertEqual(response.status_code, 403)

    # --- session auth (no API key) ---

    def test_session_auth_returns_empty(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse(URL))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    # --- API key auth ---

    def test_wrong_scope_returns_403(self):
        _, key = self._create_key(scopes=["other.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(URL))
        self.assertEqual(response.status_code, 403)
        self.assertIn("meeting.list", response.json()["detail"])
        self.assertIn("meeting.*", response.json()["detail"])

    def test_wildcard_action_scope_allowed(self):
        _, key = self._create_key(scopes=["meeting.*"])
        self._api_key_client(key)
        response = self.client.get(reverse(URL))
        self.assertEqual(response.status_code, 200)

    def test_exact_scope_allowed(self):
        _, key = self._create_key(scopes=["meeting.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(URL))
        self.assertEqual(response.status_code, 200)

    def test_revoked_key_returns_403(self):
        # DRF returns 403 (not 401) when AuthenticationFailed is raised but
        # no authenticator provides a WWW-Authenticate header.
        obj, key = self._create_key(scopes=["meeting.list"])
        obj.revoked = True
        obj.save(update_fields=["revoked"])
        self._api_key_client(key)
        response = self.client.get(reverse(URL))
        self.assertEqual(response.status_code, 403)

    def test_response_is_scoped_to_key_meeting(self):
        _, key = self._create_key(scopes=["meeting.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(URL))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pk"], self.meeting.pk)
        self.assertEqual(data["title"], self.meeting.title)
        self.assertEqual(data["state"], self.meeting.state)
