from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.core.testing import PermissionTesterMixin
from voteit.meeting.models import Meeting

User = get_user_model()


class AgendaItemViewTestCase(PermissionTesterMixin, APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.other_meeting: Meeting = Meeting.objects.create(
            title="Other meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing AI", tags=["hello", "world"]
        )
        cls.ai_private = cls.meeting.agenda_items.create(title="Private AI")
        cls.participant: User = cls.meeting.participants.get(username="participant")
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")

    def test_create(self):
        url = reverse("agendaitem-list")
        data = {
            "title": "Item no 1",
            "meeting": self.meeting.pk,
        }
        self.run_permission_tests(
            url=url,
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.moderator, 201],
                [self.participant, 403],
            ],
        )

    def test_create_meeting_ne(self):
        url = reverse("agendaitem-list")
        data = {
            "title": "Stuff",
            "meeting": -1,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual(
            {"meeting": ['Invalid pk "-1" - object does not exist.']}, data
        )

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

    def test_list_other(self):
        url = reverse("agendaitem-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.run_permission_tests(
            url=url,
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.outsider, 403, []],
            ],
        )

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
            "tags": ["aa", "bb"],
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(["aa", "bb"], data["tags"])

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


class ExportParticipantsViewSetTests(PermissionTesterMixin, APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def test_permissions(self):
        url = reverse("export-agenda-items-json", kwargs={"pk": self.meeting.pk})
        self.run_permission_tests(
            url=url,
            method="get",
            expected=[[None, 401], [self.participant, 404], [self.moderator, 200]],
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
