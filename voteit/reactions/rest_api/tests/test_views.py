from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.agenda.models import AgendaItem
from voteit.core.testing import run_permission_tests
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.proposal.models import Proposal

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


class ReactionButtonActionsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.reactions.models import ReactionButton

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.moderator: User = User.objects.create_user("mod_actions")
        cls.moderator2: User = User.objects.create_user("mod_actions2")
        cls.participant: User = User.objects.create_user("participant_actions")
        cls.outsider: User = User.objects.create_user("outsider_actions")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.meeting.add_roles(cls.moderator2, ROLE_MODERATOR)
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.button: ReactionButton = ReactionButton.objects.create(
            meeting=cls.meeting,
            title="Thumbs up",
            color="primary",
            icon="mdi-thumb-up",
            change_roles=[ROLE_PARTICIPANT],
            list_roles=[ROLE_PARTICIPANT],
            allowed_models=["proposal"],
        )
        cls.flag_button: ReactionButton = ReactionButton.objects.create(
            meeting=cls.meeting,
            title="Flag",
            color="red",
            icon="mdi-flag",
            flag_mode=True,
            allowed_models=["proposal"],
        )
        ai = AgendaItem.objects.create(meeting=cls.meeting)
        cls.proposal: Proposal = Proposal.objects.create(agenda_item=ai)
        cls.target_ct = ContentType.objects.get_for_model(Proposal)
        cls.target_data = {"content_type": "proposal", "object_id": cls.proposal.pk}

    def _mk_reaction(self, button, user):
        from voteit.reactions.models import Reaction

        return Reaction.objects.create(
            content_type=self.target_ct,
            object_id=self.proposal.pk,
            button=button,
            user=user,
        )

    # --- set ---

    def test_set_invalid_content_type(self):
        url = reverse("reaction-buttons-set", kwargs={"pk": self.button.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url, {"content_type": "meeting", "object_id": self.meeting.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.json())
        self.assertIn("content_type", response.json())

    def test_set_creates_reaction(self):
        url = reverse("reaction-buttons-set", kwargs={"pk": self.button.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, self.target_data, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        response2 = self.client.post(url, self.target_data, format="json")
        self.assertEqual(response2.status_code, 200)

    def test_set_returns_serialized_reaction(self):
        url = reverse("reaction-buttons-set", kwargs={"pk": self.button.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, self.target_data, format="json")
        data = response.json()
        self.assertIn("pk", data)
        self.assertIn("button", data)
        self.assertIn("user", data)
        self.assertEqual(data["button"], self.button.pk)
        self.assertEqual(data["user"], self.participant.pk)

    def test_set_non_flag_permissions(self):
        url = reverse("reaction-buttons-set", kwargs={"pk": self.button.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            data=self.target_data,
            method="POST",
            expected=[
                [None, 401],
                [self.outsider, 404],
                [self.participant, 201],
                [self.moderator, 201],
            ],
        ):
            func(*args)

    def test_set_flag_permissions(self):
        url = reverse("reaction-buttons-set", kwargs={"pk": self.flag_button.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            data=self.target_data,
            method="POST",
            expected=[
                [None, 401],
                [self.outsider, 404],
                [self.participant, 403],
                [self.moderator, 201],
            ],
        ):
            func(*args)

    # --- remove ---

    def test_remove_own_reaction(self):
        self._mk_reaction(self.button, self.participant)
        url = reverse("reaction-buttons-remove", kwargs={"pk": self.button.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, self.target_data, format="json")
        self.assertEqual(response.status_code, 204)
        response2 = self.client.post(url, self.target_data, format="json")
        self.assertEqual(response2.status_code, 204)

    def test_remove_non_flag_permissions(self):
        self._mk_reaction(self.button, self.participant)
        url = reverse("reaction-buttons-remove", kwargs={"pk": self.button.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            data=self.target_data,
            method="POST",
            expected=[
                [None, 401],
                [self.outsider, 404],
                [self.participant, 204],
                [self.moderator, 204],
            ],
        ):
            func(*args)

    def test_remove_does_not_remove_other_users_reaction(self):
        self._mk_reaction(self.button, self.moderator)
        url = reverse("reaction-buttons-remove", kwargs={"pk": self.button.pk})
        self.client.force_login(self.participant)
        self.client.post(url, self.target_data, format="json")
        from voteit.reactions.models import Reaction

        self.assertTrue(
            Reaction.objects.filter(button=self.button, user=self.moderator).exists()
        )

    def test_remove_flag_moderator_removes_any(self):
        self._mk_reaction(self.flag_button, self.moderator)
        url = reverse("reaction-buttons-remove", kwargs={"pk": self.flag_button.pk})
        self.client.force_login(self.moderator2)
        response = self.client.post(url, self.target_data, format="json")
        self.assertEqual(response.status_code, 204)
        from voteit.reactions.models import Reaction

        self.assertFalse(Reaction.objects.filter(button=self.flag_button).exists())

    def test_remove_flag_non_moderator(self):
        url = reverse("reaction-buttons-remove", kwargs={"pk": self.flag_button.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            data=self.target_data,
            method="POST",
            expected=[
                [None, 401],
                [self.outsider, 404],
                [self.participant, 403],
                [self.moderator, 204],
            ],
        ):
            func(*args)

    # --- list_reactions ---

    def test_list_reactions_permissions(self):
        url = reverse("reaction-buttons-list-reactions", kwargs={"pk": self.button.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            data=self.target_data,
            method="POST",
            expected=[
                [None, 401],
                [self.outsider, 404],
                [self.participant, 200],
                [self.moderator, 200],
            ],
        ):
            func(*args)

    def test_list_reactions_content(self):
        self._mk_reaction(self.button, self.participant)
        self._mk_reaction(self.button, self.moderator)
        url = reverse("reaction-buttons-list-reactions", kwargs={"pk": self.button.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, self.target_data, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            response.json()["users"], [self.participant.pk, self.moderator.pk]
        )

    # --- set: 404 for invalid object_id (bug 1 regression) ---

    def test_set_nonexistent_object_id_returns_404(self):
        url = reverse("reaction-buttons-set", kwargs={"pk": self.button.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url, {"content_type": "proposal", "object_id": 999999}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_set_object_from_other_meeting_returns_404(self):
        other_meeting = Meeting.objects.create(title="Other", state="ongoing")
        other_ai = AgendaItem.objects.create(meeting=other_meeting)
        other_proposal = Proposal.objects.create(agenda_item=other_ai)
        url = reverse("reaction-buttons-set", kwargs={"pk": self.button.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url, {"content_type": "proposal", "object_id": other_proposal.pk}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    # --- flag singleton enforcement (bug 2 regression) ---

    def test_set_flag_second_moderator_does_not_create_duplicate(self):
        from voteit.reactions.models import Reaction

        url = reverse("reaction-buttons-set", kwargs={"pk": self.flag_button.pk})
        self.client.force_login(self.moderator)
        response1 = self.client.post(url, self.target_data, format="json")
        self.assertEqual(response1.status_code, 201)

        self.client.force_login(self.moderator2)
        response2 = self.client.post(url, self.target_data, format="json")
        self.assertEqual(response2.status_code, 200)

        self.assertEqual(
            Reaction.objects.filter(
                button=self.flag_button,
                content_type=self.target_ct,
                object_id=self.proposal.pk,
            ).count(),
            1,
        )
