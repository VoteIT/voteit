from django.urls import reverse
from rest_framework.test import APITestCase


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
        cls.meeting.add_roles(cls.moderator, "moderator")
        cls.url = reverse("meeting-transitions", kwargs={"pk": cls.meeting.pk})

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_get_list_with_nested_translations(self):
        self.client.force_login(self.moderator)
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="sv")
        self.assertEqual(200, response.status_code)
        # Break out the transition to ongoing
        transition = None
        for x in response.json():
            if x.get("target") == "ongoing":
                transition = x
                break
        self.assertIsNotNone(transition)
        self.assertEqual("sv", response.headers.get("Content-Language"))
        self.assertEqual("Gör pågående", transition["title"])

    def test_missing_field(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url, data={"bla": "haha"}, HTTP_ACCEPT_LANGUAGE="sv"
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("sv", response.headers.get("Content-Language"))
        data = response.json()
        # No clue why this is a list but we're testing translations here :)
        self.assertEqual(["Det här fältet är obligatoriskt."], data["transition"])

    def test_bad_transition(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url, data={"transition": "hello"}, HTTP_ACCEPT_LANGUAGE="sv"
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("sv", response.headers.get("Content-Language"))
        data = response.json()
        self.assertEqual("Ogiltig handling: hello", data["transition"])

    def test_no_obj(self):
        url = reverse("meeting-transitions", kwargs={"pk": 0})
        self.client.force_login(self.moderator)
        response = self.client.post(
            url, data={"transition": "hello"}, HTTP_ACCEPT_LANGUAGE="sv"
        )
        self.assertEqual("sv", response.headers.get("Content-Language"))
        data = response.json()
        self.assertEqual("Hittades inte.", data["detail"])

    def test_unauthenticated(self):
        response = self.client.post(
            self.url, data={"transition": "ongoing"}, HTTP_ACCEPT_LANGUAGE="sv"
        )
        self.assertEqual("sv", response.headers.get("Content-Language"))
        data = response.json()
        self.assertEqual("Autentiseringsuppgifter ej tillhandahållna.", data["detail"])

    def test_bad_permission(self):
        self.meeting.remove_roles(self.moderator, "moderator")
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
