from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from voteit.token_api.validators import validate_api_key_scopes
from voteit.organisation.models import Organisation

User = get_user_model()


class ValidateApiKeyScopesTest(TestCase):
    def test_valid_exact_scope(self):
        validate_api_key_scopes(["meeting.list"])  # no exception

    def test_valid_wildcard_action(self):
        validate_api_key_scopes(["meeting.*"])  # no exception

    def test_empty_list_is_valid(self):
        validate_api_key_scopes([])  # no exception

    def test_missing_separator_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_api_key_scopes(["meetinglist"])
        self.assertIn("expected '<resource>.<action>'", str(ctx.exception))

    def test_unknown_resource_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_api_key_scopes(["unknown.list"])
        self.assertIn("Unknown resource 'unknown'", str(ctx.exception))

    def test_unknown_action_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_api_key_scopes(["meeting.destroy"])
        self.assertIn("Unknown action 'destroy'", str(ctx.exception))
        self.assertIn("'meeting'", str(ctx.exception))

    def test_multiple_scopes_first_invalid_raises(self):
        with self.assertRaises(ValidationError):
            validate_api_key_scopes(["meeting.list", "bad"])

    def test_multiple_valid_scopes(self):
        validate_api_key_scopes(["meeting.list", "meeting.*"])  # no exception


class ScopeValidationViaApiTest(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.meeting = cls.org.meetings.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")

    def _post_scopes(self, scopes):
        self.client.force_login(self.moderator)
        return self.client.post(
            reverse("meeting-api-token-list"),
            {"name": "Key", "scopes": scopes, "meeting": self.meeting.pk},
        )

    def test_valid_scope_accepted(self):
        response = self._post_scopes(["meeting.list"])
        self.assertEqual(response.status_code, 201)

    def test_invalid_format_rejected(self):
        response = self._post_scopes(["meetinglist"])
        self.assertEqual(response.status_code, 400)

    def test_unknown_resource_rejected(self):
        response = self._post_scopes(["ghost.list"])
        self.assertEqual(response.status_code, 400)

    def test_unknown_action_rejected(self):
        response = self._post_scopes(["meeting.delete"])
        self.assertEqual(response.status_code, 400)
