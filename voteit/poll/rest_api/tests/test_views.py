from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase


User = get_user_model()


class PollViewSetTests(APITestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting",
        )
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        self.ai_private = self.meeting.agenda_items.create(title="Private")
        self.prop = self.ai.proposals.create()
        self.participant: User = User.objects.create_user("participant")
        self.moderator: User = User.objects.create_user("moderator")
        self.outsider: User = User.objects.create_user("outsider")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)

    def test_create(self):
        url = reverse("poll-list")
        data = {
            "title": "Let's vote",
            "meeting": self.meeting.pk,
            "method_name": "simple",
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk],
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_create_wrong_user(self):
        url = reverse("poll-list")
        data = {
            "title": "Let's vote",
            "meeting": self.meeting.pk,
            "method_name": "simple",
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk],
        }
        for user, status in (
            (None, 401),
            (self.participant, 403),
            (self.outsider, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_no_method_name(self):
        url = reverse("poll-list")
        data = {
            "title": "Let's vote",
            "meeting": self.meeting.pk,
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk],
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("method_name", response.json())
