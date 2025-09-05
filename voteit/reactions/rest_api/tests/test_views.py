from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT

if TYPE_CHECKING:
    from voteit.reactions.models import ReactionButton

User = get_user_model()


class ReactionButtonViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def _mk_one(self) -> ReactionButton:
        from voteit.reactions.models import ReactionButton

        return ReactionButton.objects.create(
            meeting=self.meeting,
            title="Thumbs up",
            color="primary",
            icon="mdi-thumb-up",
        )

    def test_create(self):
        url = reverse("reaction-buttons-list")
        data = {
            "title": "Gilla",
            "meeting": self.meeting.pk,
            "icon": "mdi-thumb-up",
            "color": "primary",
            "change_roles": [],
            "list_roles": [],
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            201,
        )
        self.assertTrue(self.meeting.reaction_buttons.exists())

    def test_create_duplicate(self):
        one = self._mk_one()
        one.title = "Hello"
        one.save()
        two = self._mk_one()
        url = reverse("reaction-buttons-detail", kwargs={"pk": two.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(
            url,
            data={
                "title": "hello",  # Case-insensitive!
            },
        )
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual(
            {"title": ["Duplicate title, change at least color or icon."]}, data
        )

    def test_create_bad_users(self):
        url = reverse("reaction-buttons-list")
        data = {
            "title": "Gilla",
            "meeting": self.meeting.pk,
            "icon": "mdi-thumb-up",
            "color": "primary",
        }
        for user, status in (
            (None, 401),
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

    def test_create_system_ne(self):
        url = reverse("reaction-buttons-list")
        data = {
            "title": "Gilla",
            "meeting": -1,
            "icon": "mdi-thumb-up",
            "color": "primary",
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_list(self):
        url = reverse("reaction-buttons-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json())

    def test_get(self):
        button = self._mk_one()
        url = reverse("reaction-buttons-detail", kwargs={"pk": button.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(button.pk, data["pk"])
        self.assertEqual(self.meeting.pk, data["meeting"])

    def test_delete(self):
        button = self._mk_one()
        url = reverse("reaction-buttons-detail", kwargs={"pk": button.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, button.refresh_from_db)

    def test_delete_participant(self):
        button = self._mk_one()
        url = reverse("reaction-buttons-detail", kwargs={"pk": button.pk})
        self.client.force_login(self.participant)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_edit_causes_duplicate(self):
        self._mk_one()
        url = reverse("reaction-buttons-list")
        self.client.force_login(self.moderator)
        response = self.client.post(
            url,
            data={
                "meeting": self.meeting.pk,
                "title": "Thumbs up",
                "color": "primary",
                "icon": "mdi-thumb-up",
                "change_roles": [],
                "list_roles": [],
            },
        )
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual(
            {"title": ["Duplicate title, change at least color or icon."]}, data
        )
