from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

if TYPE_CHECKING:
    from voteit.core.rest_api.mixins import TransitionsMixin

User = get_user_model()


class TransitionsMixinTests(APITestCase):
    """
    We'll test this view against the regular meeting endpoint
    """

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation

        org = Organisation.objects.create()
        cls.meeting = Meeting.objects.create(
            er_policy_name="auto_before_poll", organisation=org
        )
        cls.moderator = cls.meeting.participants.create(
            username="moderator", organisation=org
        )
        cls.meeting.add_roles(cls.moderator, "moderator")

    def setUp(self):
        self.meeting.refresh_from_db()

    @property
    def _cut(self):
        from voteit.core.rest_api.mixins import TransitionsMixin

        return TransitionsMixin

    @property
    def _url(self):
        return reverse("meeting-transitions", kwargs={"pk": self.meeting.pk})

    def test_available_upcoming(self):
        self.client.force_login(self.moderator)
        response = self.client.get(self._url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {
                    "name": "ongoing",
                    "permission": "meeting.moderate_meeting",
                    "source": "upcoming",
                    "target": "ongoing",
                    "title": "Make ongoing",
                }
            ],
            response.json(),
        )

    def test_available_ongoing(self):
        self.meeting.ongoing()
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.get(self._url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {
                    "name": "close",
                    "permission": "meeting.moderate_meeting",
                    "source": "ongoing",
                    "target": "closed",
                    "title": "Close",
                },
                {
                    "name": "upcoming",
                    "permission": "meeting.moderate_meeting",
                    "source": "ongoing",
                    "target": "upcoming",
                    "title": "Back to upcoming",
                },
            ],
            response.json(),
        )

    def test_do_transition(self):
        self.client.force_login(self.moderator)
        response = self.client.post(self._url, data={"transition": "ongoing"})
        self.assertEqual(201, response.status_code)
        self.meeting.refresh_from_db()
        self.assertEqual("ongoing", self.meeting.state)


class TransitionMixinAgendaTest(APITestCase):
    """
    Since transition is a mixin, we'll test it against agenda
    """

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

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

    def test_transition_moderator(self):
        url = reverse("agendaitem-transitions", kwargs={"pk": self.ai.pk})
        data = {"transition": "upcoming"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_bad_transition_moderator(self):
        url = reverse("agendaitem-transitions", kwargs={"pk": self.ai.pk})
        data = {"transition": "wooohoooo"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_transition_unauthorized_users(self):
        url = reverse("agendaitem-transitions", kwargs={"pk": self.ai.pk})
        data = {"transition": "upcoming"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 401)
        self.client.force_login(self.participant)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

    def test_transition_conditions_not_met(self):
        self.meeting.state = "upcoming"
        self.meeting.save()
        url = reverse("agendaitem-transitions", kwargs={"pk": self.ai_private.pk})
        data = {"transition": "ongoing"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
