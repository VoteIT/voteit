import os
import tempfile

import yaml
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(_TESTS_DIR, "fixtures")

User = get_user_model()


class MeetingDataImportViewTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)

    def test_empty_file(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-detail", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES, "empty.txt"), "rb") as f:
            response = self.client.put(url, data={"file": f}, format="multipart")
        self.assertContains(
            response,
            "The submitted file is empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_junk_file(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-detail", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES, "junk.txt"), "rb") as f:
            response = self.client.put(url, data={"file": f}, format="multipart")
        self.assertContains(
            response,
            "Import file malformed, must be key-value data",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_bad_version(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-detail", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES, "bad_version.yaml"), "rb") as f:
            response = self.client.put(url, data={"file": f}, format="multipart")
        self.assertContains(
            response,
            "Wrong file version",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_empty_import(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-detail", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES, "empty_import.yaml"), "rb") as f:
            response = self.client.put(url, data={"file": f}, format="multipart")
        self.assertContains(
            response,
            "File doesn't contain any",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def test_ais_and_groups(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-detail", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.put(
                url, data={"file": f, "commit": "1"}, format="multipart"
            )
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual(
            {
                "agenda_items": 3,
                "diff_proposals": 0,
                "discussion_posts": 0,
                "groups": 1,
                "proposals": 1,
                "text_documents": 0,
            },
            response.json(),
        )
        self.assertEqual(
            ["Crisps", "Hot dogs", "Pickles"],
            list(
                self.meeting.agenda_items.values_list("title", flat=True).order_by(
                    "title"
                )
            ),
        )
        self.assertEqual(
            ["The Hellos"],
            list(self.meeting.groups.values_list("title", flat=True).order_by("title")),
        )

    def test_ais_and_groups_dryrun(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-detail", kwargs={"pk": self.meeting.pk})
        with open(os.path.join(FIXTURES, "ais_and_groups.yaml"), "rb") as f:
            response = self.client.put(url, data={"file": f}, format="multipart")
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(
            {
                "agenda_items": 3,
                "diff_proposals": 0,
                "discussion_posts": 0,
                "groups": 1,
                "proposals": 1,
                "text_documents": 0,
            },
            response.json(),
        )
        self.assertEqual(
            [],
            list(
                self.meeting.agenda_items.values_list("title", flat=True).order_by(
                    "title"
                )
            ),
        )


class MeetingDataExportViewTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.organisation = cls.meeting.organisation
        cls.new_meeting = cls.organisation.meetings.create()
        cls.new_meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def test_json(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-json", kwargs={"pk": self.meeting.pk})
        response = self.client.post(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertEqual("The Hellos", data["groups"][0]["title"])

    def test_yaml(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-yaml", kwargs={"pk": self.meeting.pk})
        response = self.client.post(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = yaml.safe_load(response.content)
        self.assertEqual("The Hellos", data["groups"][0]["title"])

    def test_json_round_trip(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-json", kwargs={"pk": self.meeting.pk})
        response = self.client.post(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        url = reverse("meeting-data-detail", kwargs={"pk": self.new_meeting.pk})
        with tempfile.NamedTemporaryFile(suffix=".json") as tmp_file:
            tmp_file.write(response.content)
            tmp_file.seek(0)
            response = self.client.put(
                url, data={"file": tmp_file, "commit": 1}, format="multipart"
            )
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual(
            ["Crisps", "Hot dogs", "Pickles"],
            list(
                self.new_meeting.agenda_items.values_list("title", flat=True).order_by(
                    "title"
                )
            ),
        )

    def test_yaml_round_trip(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-yaml", kwargs={"pk": self.meeting.pk})
        response = self.client.post(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        url = reverse("meeting-data-detail", kwargs={"pk": self.new_meeting.pk})
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp_file:
            tmp_file.write(response.content)
            tmp_file.seek(0)
            response = self.client.put(
                url, data={"file": tmp_file, "commit": 1}, format="multipart"
            )
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual(
            ["Crisps", "Hot dogs", "Pickles"],
            list(
                self.new_meeting.agenda_items.values_list("title", flat=True).order_by(
                    "title"
                )
            ),
        )

    def test_json_exclude_groups(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-json", kwargs={"pk": self.meeting.pk})
        response = self.client.post(
            url, data={"include_groups": 0, "clear_group_authors": 1}
        )
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        data = response.json()
        self.assertEqual([], data["groups"])

    def test_json_exclude_groups_bad_combination(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-data-json", kwargs={"pk": self.meeting.pk})
        response = self.client.post(url, data={"include_groups": 0})
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        data = response.json()
        self.assertEqual(
            {
                "include_groups": "Groups are needed to set group authors - change 'clear_group_authors' or 'include_groups'"
            },
            data,
        )
