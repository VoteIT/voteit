from typing import TYPE_CHECKING

from django.urls import reverse
from rest_framework.test import APITestCase


if TYPE_CHECKING:
    from voteit.core.rest_api.mixins import TransitionsMixin


class TransitionsMixinTests(APITestCase):
    """ We'll test this view against the regular meeting endpoint"""

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation

        org = Organisation.objects.create()
        cls.meeting = Meeting.objects.create(er_policy_name="auto_before_poll", organisation=org)
        cls.moderator = cls.meeting.participants.create(username="moderator", organisation=org)
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
