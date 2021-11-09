from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase


User = get_user_model()


class AgendaItemViewTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def setUp(self):
        self.meeting.refresh_from_db()
        self.ai.refresh_from_db()

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
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_get(self):
        url = reverse("agendaitem-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))

    def test_transition_moderator(self):
        url = f"/api/agenda-items/{self.ai.pk}/transitions/"
        data = {"transition": "upcoming"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_bad_transition_moderator(self):
        url = f"/api/agenda-items/{self.ai.pk}/transitions/"
        data = {"transition": "wooohoooo"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_transition_unauthorized_users(self):
        url = f"/api/agenda-items/{self.ai.pk}/transitions/"
        data = {"transition": "upcoming"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 401)
        self.client.force_login(self.participant)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

    def test_transition_conditions_not_met(self):
        self.meeting.state = "upcoming"
        self.meeting.save()
        url = f"/api/agenda-items/{self.ai_private.pk}/transitions/"
        data = {"transition": "ongoing"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            400,
        )
