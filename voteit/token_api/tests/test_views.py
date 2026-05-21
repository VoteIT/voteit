from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.meeting.workflows import MeetingWf
from voteit.token_api.models import MeetingAPIKey
from voteit.token_api.models import create_api_key_user
from voteit.organisation.models import Organisation

User = get_user_model()


class MeetingApiTokenViewSetTest(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.meeting = cls.org.meetings.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def _create_key(self, name="Test key", scopes=None):
        api_user = create_api_key_user(self.meeting)
        obj, key = MeetingAPIKey.objects.create_key(
            name=name,
            scopes=scopes or [],
            meeting=self.meeting,
            user=api_user,
        )
        return obj, key

    def _close_meeting(self):
        self.meeting.state = MeetingWf.CLOSED
        self.meeting.save(update_fields=["state"])

    # --- list ---

    def test_list_returns_keys_for_moderator(self):
        self._create_key()
        self.client.force_login(self.moderator)
        response = self.client.get(
            reverse("meeting-api-token-list"), {"meeting": self.meeting.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_list_empty_for_non_moderator(self):
        self._create_key()
        self.client.force_login(self.participant)
        response = self.client.get(
            reverse("meeting-api-token-list"), {"meeting": self.meeting.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_list_requires_authentication(self):
        response = self.client.get(
            reverse("meeting-api-token-list"), {"meeting": self.meeting.pk}
        )
        self.assertEqual(response.status_code, 401)

    # --- create ---

    def test_create_returns_key_and_object(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("meeting-api-token-list"),
            {"name": "My key", "scopes": ["meeting.list"], "meeting": self.meeting.pk},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("key", data)
        self.assertIn(".", data["key"])  # keys have the prefix.secret format

    def test_create_generates_inactive_api_user(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("meeting-api-token-list"),
            {"name": "My key", "scopes": [], "meeting": self.meeting.pk},
        )
        self.assertEqual(response.status_code, 201)
        obj = MeetingAPIKey.objects.get(prefix=response.json()["prefix"])
        self.assertFalse(obj.user.is_active)
        self.assertTrue(obj.user.username.startswith("apikey-"))
        self.assertEqual(obj.user.organisation, self.org)
        self.assertFalse(obj.user.has_usable_password())

    def test_create_sets_expiry_date_120_days(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("meeting-api-token-list"),
            {"name": "My key", "scopes": [], "meeting": self.meeting.pk},
        )
        self.assertEqual(response.status_code, 201)
        obj = MeetingAPIKey.objects.get(prefix=response.json()["prefix"])
        expected = timezone.now() + timedelta(days=120)
        self.assertAlmostEqual(obj.expiry_date, expected, delta=timedelta(seconds=5))

    def test_create_forbidden_for_participant(self):
        self.client.force_login(self.participant)
        response = self.client.post(
            reverse("meeting-api-token-list"),
            {"name": "My key", "scopes": [], "meeting": self.meeting.pk},
        )
        self.assertEqual(response.status_code, 403)

    # --- retrieve ---

    def test_retrieve_returns_key_object(self):
        obj, _ = self._create_key()
        self.client.force_login(self.moderator)
        response = self.client.get(
            reverse("meeting-api-token-detail", args=[obj.prefix])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("key", response.json())

    def test_retrieve_not_found_for_non_moderator(self):
        obj, _ = self._create_key()
        self.client.force_login(self.participant)
        response = self.client.get(
            reverse("meeting-api-token-detail", args=[obj.prefix])
        )
        self.assertEqual(response.status_code, 404)

    # --- destroy (revoke) ---

    def test_destroy_revokes_key_without_deleting(self):
        obj, _ = self._create_key()
        self.client.force_login(self.moderator)
        response = self.client.delete(
            reverse("meeting-api-token-detail", args=[obj.prefix])
        )
        self.assertEqual(response.status_code, 204)
        obj.refresh_from_db()
        self.assertTrue(obj.revoked)

    def test_destroy_forbidden_for_participant(self):
        obj, _ = self._create_key()
        self.client.force_login(self.participant)
        response = self.client.delete(
            reverse("meeting-api-token-detail", args=[obj.prefix])
        )
        self.assertEqual(response.status_code, 404)

    # --- cycle ---

    def test_cycle_returns_new_key(self):
        obj, _ = self._create_key(name="Cycle me")
        old_prefix = obj.prefix
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("meeting-api-token-cycle", args=[old_prefix])
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("key", data)
        self.assertNotEqual(data["prefix"], old_prefix)

    def test_cycle_deletes_old_key(self):
        obj, _ = self._create_key()
        old_pk = obj.pk
        self.client.force_login(self.moderator)
        self.client.post(reverse("meeting-api-token-cycle", args=[obj.prefix]))
        self.assertFalse(MeetingAPIKey.objects.filter(pk=old_pk).exists())

    def test_cycle_creates_new_api_user(self):
        obj, _ = self._create_key()
        old_user_pk = obj.user_id
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("meeting-api-token-cycle", args=[obj.prefix])
        )
        new_obj = MeetingAPIKey.objects.get(prefix=response.json()["prefix"])
        self.assertNotEqual(new_obj.user_id, old_user_pk)
        self.assertFalse(new_obj.user.is_active)

    def test_cycle_forbidden_for_participant(self):
        obj, _ = self._create_key()
        self.client.force_login(self.participant)
        response = self.client.post(
            reverse("meeting-api-token-cycle", args=[obj.prefix])
        )
        self.assertEqual(response.status_code, 404)

    # --- finished meeting ---

    def test_create_blocked_when_meeting_finished(self):
        self._close_meeting()
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("meeting-api-token-list"),
            {"name": "Key", "scopes": [], "meeting": self.meeting.pk},
        )
        self.assertEqual(response.status_code, 403)

    def test_cycle_blocked_when_meeting_finished(self):
        obj, _ = self._create_key()
        self._close_meeting()
        self.client.force_login(self.moderator)
        response = self.client.post(
            reverse("meeting-api-token-cycle", args=[obj.prefix])
        )
        self.assertEqual(response.status_code, 403)

    # --- scopes ---

    def test_scopes_returns_list_without_authentication(self):
        response = self.client.get(reverse("meeting-api-token-scopes"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertIn("meeting.*", data)
        self.assertIn("meeting.list", data)
        self.assertIn("invites.*", data)

    def test_scopes_includes_wildcard_before_actions(self):
        response = self.client.get(reverse("meeting-api-token-scopes"))
        data = response.json()
        for resource in ("meeting", "invites"):
            wildcard_idx = data.index(f"{resource}.*")
            action_indices = [
                i for i, s in enumerate(data) if s.startswith(f"{resource}.") and s != f"{resource}.*"
            ]
            self.assertTrue(all(wildcard_idx < i for i in action_indices))

    # --- finished meeting ---

    def test_destroy_allowed_when_meeting_finished(self):
        obj, _ = self._create_key()
        self._close_meeting()
        self.client.force_login(self.moderator)
        response = self.client.delete(
            reverse("meeting-api-token-detail", args=[obj.prefix])
        )
        self.assertEqual(response.status_code, 204)
        obj.refresh_from_db()
        self.assertTrue(obj.revoked)
