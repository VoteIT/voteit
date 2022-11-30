from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()


class AgendaItemViewTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.other_meeting: Meeting = Meeting.objects.create(
            title="Other meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing", tags=["hello", "world"]
        )
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def setUp(self):
        self.meeting.refresh_from_db()
        self.ai.refresh_from_db()

    def test_create(self):
        url = reverse("agendaitem-list")
        data = {
            "title": "Item no 1",
            "meeting": self.meeting.pk,
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
            (self.participant, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_meeting_ne(self):
        url = reverse("agendaitem-list")
        data = {
            "title": "Stuff",
            "meeting": -1,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_list(self):
        url = reverse("agendaitem-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))

    def test_list_participant(self):
        url = reverse("agendaitem-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.participant)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_list_anon(self):
        url = reverse("agendaitem-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_list_outsider(self):
        url = reverse("agendaitem-list")
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([], response.json())

    def test_patch_change_meeting(self):
        url = reverse("agendaitem-detail", kwargs={"pk": self.ai.pk})
        data = {
            "meeting": self.other_meeting.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.meeting.pk, data["meeting"])

    def test_patch_change_tags(self):
        url = reverse("agendaitem-detail", kwargs={"pk": self.ai.pk})
        data = {
            "tags": ["a", "b"],
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(["a", "b"], data["tags"])

    def test_patch_remove_tags(self):
        url = reverse("agendaitem-detail", kwargs={"pk": self.ai.pk})
        data = {
            "tags": [],
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([], data["tags"])


class ExportParticipantsViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def test_not_allowed(self):
        url = reverse("export-agenda-items-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertContains(
            response, "permission meeting.moderate_meeting", status_code=403
        )

    def test_json(self):
        url = reverse("export-agenda-items-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(3, len(data))
        self.assertEqual(
            {
                "body": "could be tasty",
                "pk": 1,
                "state": "upcoming",
                "tags": "",
                "title": "Pickles",
            },
            data[0],
        )

    def test_csv(self):
        url = reverse("export-agenda-items-csv", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/csv", response.headers.get("Content-Type"))
        rows = response.content.splitlines()
        self.assertIn(
            b"state,pk,title,body,tags",
            rows,
        )
        self.assertIn(
            b"upcoming,1,Pickles,could be tasty,",
            rows,
        )
