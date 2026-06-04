from django.urls import reverse
from rest_framework.test import APITestCase

from voteit.meeting.roles import ROLE_MODERATOR


class TranslationTests(APITestCase):
    """
    Make sure translations work in REST API
    """

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation

        org = Organisation.objects.create()
        cls.meeting: Meeting = org.meetings.create(
            er_policy_name="auto_before_poll", title="Hello"
        )
        cls.moderator = cls.meeting.participants.create(
            username="moderator", organisation=org
        )
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.url = reverse("meeting-event", kwargs={"pk": cls.meeting.pk})

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_get_state_with_language_header(self):
        self.client.force_login(self.moderator)
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="sv")
        self.assertEqual(200, response.status_code)
        self.assertEqual("sv", response.headers.get("Content-Language"))
        self.assertEqual({"state": "upcoming"}, response.json())

    def test_missing_field(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url,
            data={"bla": "haha"},
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="sv",
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("sv", response.headers.get("Content-Language"))
        data = response.json()
        self.assertIn("event", data)

    def test_bad_event(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url,
            data={"event": "hello"},
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="sv",
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("sv", response.headers.get("Content-Language"))

    def test_unauthenticated(self):
        response = self.client.post(
            self.url,
            data={"event": "make_ongoing"},
            content_type="application/json",
            HTTP_ACCEPT_LANGUAGE="sv",
        )
        self.assertEqual("sv", response.headers.get("Content-Language"))
        data = response.json()
        self.assertEqual("Autentiseringsuppgifter ej tillhandahållna.", data["detail"])

    def test_bad_permission(self):
        self.meeting.remove_roles(self.moderator, ROLE_MODERATOR)
        participant = self.moderator
        self.client.force_login(participant)
        url = reverse("meeting-detail", kwargs={"pk": self.meeting.pk})
        response = self.client.patch(
            url, HTTP_ACCEPT_LANGUAGE="sv", data={"title": "Hello"}
        )
        self.assertEqual("sv", response.headers.get("Content-Language"))
        data = response.json()
        self.assertEqual(
            "Du saknar behörigheten ’meeting.change_meeting’ på Hello.",
            data["detail"],
        )
