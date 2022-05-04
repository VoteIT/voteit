from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from rest_framework.test import APITestCase

from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()

_BASENAME = "access-policy-automatic"


class AutomaticAccessAPITests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.access_policy.app.policies import AutomaticAccess

        cls.participant: User = User.objects.get(username="participant")
        cls.moderator: User = User.objects.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.automatic_access = AutomaticAccess.objects.create(meeting=cls.meeting)

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_create(self):
        self.automatic_access.delete()
        url = reverse(f"{_BASENAME}-list")
        data = {
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
        url = reverse(f"{_BASENAME}-list")
        data = {
            "meeting": -1,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_list(self):
        url = reverse(f"{_BASENAME}-list")
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json())

    def test_list_with_meeting(self):
        url = reverse(f"{_BASENAME}-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            [
                {
                    "pk": self.automatic_access.pk,
                    "meeting": self.meeting.pk,
                    "active": False,
                    "name": "automatic",
                    "roles_given": [],
                }
            ],
            data,
        )

    def test_get(self):
        url = reverse(f"{_BASENAME}-detail", kwargs={"pk": self.automatic_access.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                "pk": self.automatic_access.pk,
                "meeting": self.meeting.pk,
                "active": False,
                "name": "automatic",
                "roles_given": [],
            },
            response.json(),
        )

    def test_patch(self):
        url = reverse(f"{_BASENAME}-detail", kwargs={"pk": self.automatic_access.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"active": True})
        self.assertEqual(response.status_code, 200)
        self.automatic_access.refresh_from_db()
        self.assertEqual(True, self.automatic_access.active)

    def test_delete(self):
        url = reverse(f"{_BASENAME}-detail", kwargs={"pk": self.automatic_access.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, self.automatic_access.refresh_from_db)

    def test_delete_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        url = reverse(f"{_BASENAME}-detail", kwargs={"pk": self.automatic_access.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_join(self):
        self.automatic_access.active = True
        self.automatic_access.roles_given = [ROLE_PARTICIPANT]
        self.automatic_access.save()
        url = reverse(f"{_BASENAME}-join", kwargs={"pk": self.automatic_access.pk})
        self.client.force_login(self.outsider)
        response = self.client.post(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.outsider))

    def test_join_not_active(self):
        self.automatic_access.active = False
        self.automatic_access.save()
        url = reverse(f"{_BASENAME}-join", kwargs={"pk": self.automatic_access.pk})
        self.client.force_login(self.outsider)
        response = self.client.post(url)
        self.assertEqual(
            response.status_code,
            400,
        )
