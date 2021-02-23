from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase


User = get_user_model()


class AgendaItemViewTestCase(APITestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        self.ai_private = self.meeting.agenda_items.create(title="Private")
        self.participant: User = User.objects.create_user("participant")
        self.moderator: User = User.objects.create_user("moderator")
        self.outsider: User = User.objects.create_user("outsider")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)

    def test_create(self):
        url = reverse("agendaitem-list")
        data = {
            "title": "Item no 1",
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
        url = reverse("agendaitem-list")
        data = {
            "title": "Stuff",
            "meeting": -1,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get("detail"), "Permission denied")

    def test_get(self):
        url = reverse("agendaitem-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 405)
