from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.core.testing import run_permission_tests
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
        for func, args in run_permission_tests(
            self,
            url=url,
            data=data,
            method="POST",
            expected=[
                [
                    self.moderator,
                    201,
                    {
                        "description": "",
                        "color": "primary",
                        "order": 0,
                        "change_roles": [],
                        "list_roles": [],
                        "allowed_models": ["proposal", "discussion_post"],
                        "target": None,
                        "flag_mode": False,
                        "vote_template": False,
                        "on_presentation": False,
                        "on_vote": False,
                        "active": True,
                    },
                ],
                [self.participant, 403],
                [self.outsider, 403],
            ],
        ):
            func(*args)

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
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertDictEqual(
            {"meeting": ['Invalid pk "-1" - object does not exist.']}, data
        )

    def test_list(self):
        btn = self._mk_one()
        url = reverse("reaction-buttons-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(400, response.status_code)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        data = response.json()
        self.assertEqual(
            200,
            response.status_code,
            data,
        )
        self.assertEqual(len(data), 1)
        self.assertSetEqual({btn.pk}, {x["pk"] for x in data})

    def test_get(self):
        button = self._mk_one()
        url = reverse("reaction-buttons-detail", kwargs={"pk": button.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            expected=[
                [
                    self.moderator,
                    200,
                    {
                        "meeting": self.meeting.pk,
                        "title": "Thumbs up",
                        "color": "primary",
                        "icon": "mdi-thumb-up",
                    },
                ],
                [self.participant, 200],
                [self.outsider, 404],
            ],
        ):
            func(*args)

    def test_delete(self):
        button = self._mk_one()
        url = reverse("reaction-buttons-detail", kwargs={"pk": button.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            method="delete",
            expected=[
                [
                    self.moderator,
                    204,
                ],
                [self.participant, 403],
                [self.outsider, 404],
            ],
        ):
            func(*args)

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
