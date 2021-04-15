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

        cls.meeting = Meeting.objects.create(er_policy_name="auto_before_poll")
        cls.moderator = cls.meeting.participants.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, "moderator")

    def setUp(self):
        self.meeting.refresh_from_db()

    @property
    def _cut(self):
        from voteit.core.rest_api.mixins import TransitionsMixin

        return TransitionsMixin

    def test_available_upcoming(self):
        url = reverse("meeting-transitions", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
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
        url = reverse("meeting-transitions", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
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
        url = reverse("meeting-transitions", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, data={"transition": "ongoing"})
        self.assertEqual(201, response.status_code)
        self.meeting.refresh_from_db()
        self.assertEqual("ongoing", self.meeting.state)
