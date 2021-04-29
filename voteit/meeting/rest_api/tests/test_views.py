from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting

User = get_user_model()


class MeetingViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)

    def test_create(self):
        url = reverse("meeting-list")
        data = {"title": "Hello world"}
        participant = User.objects.get(username="participant")
        org_manager = User.objects.get(username="org_manager")
        for user, status in (
            (None, 401),
            (org_manager, 201),
            (participant, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_meeting_org_fetched_from_user(self):
        url = reverse("meeting-list")
        data = {
            "title": "Stuff",
            "organisation": -1,
        }
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertEqual(meeting.organisation.pk, 1)

    def test_create_creator_becomes_moderator(self):
        url = reverse("meeting-list")
        data = {"title": "Hello world"}
        org_manager = User.objects.get(username="org_manager")
        self.client.force_login(org_manager)
        response = self.client.post(url, data)
        data = response.json()
        meeting = Meeting.objects.get(pk=data["pk"])
        self.assertTrue(meeting.has_roles(org_manager, "moderator"))

    def test_get(self):
        url = reverse("meeting-list")
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_transition_moderator(self):
        url = reverse("meeting-transitions", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")

        # url = f"/api/meeting-invites/{self.invite.pk}/transitions/"
        data = {"transition": "ongoing"}
        self.client.force_login(moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_bad_transition_moderator(self):
        # url = f"/api/meeting-invites/{self.invite.pk}/transitions/"
        url = reverse("meeting-transitions", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        data = {"transition": "wooohoooo"}
        self.client.force_login(moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_transition_unauthorized_users(self):
        # url = f"/api/meeting-invites/{self.invite.pk}/transitions/"
        url = reverse("meeting-transitions", kwargs={"pk": 1})
        data = {"transition": "ongoing"}
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            401,
        )
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            400,  # Raises invalid transition
        )

    def test_delete(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_delete_participant(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        participant = User.objects.get(username="participant")
        self.client.force_login(participant)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_archived(self):
        self.meeting.archive()
        self.meeting.save()
        url = reverse("meeting-detail", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_change(self):
        url = reverse("meeting-detail", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.patch(url, {"title": "A brave new title"})
        self.assertEqual(response.status_code, 200)
        self.meeting.refresh_from_db()
        self.assertEqual("A brave new title", self.meeting.title)

    def test_change_archived(self):
        self.meeting.archive()
        self.meeting.save()
        url = reverse("meeting-detail", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.patch(url, {"title": "Not allowed"})
        self.assertEqual(response.status_code, 403)

    def test_change_agenda_order(self):
        url = reverse("meeting-set-agenda-order", kwargs={"pk": 1})
        moderator = User.objects.get(username="moderator")
        self.client.force_login(moderator)
        response = self.client.post(url, {"order": [3, 1, 2]})
        self.assertEqual(201, response.status_code)
        one = AgendaItem.objects.get(pk=1)
        two = AgendaItem.objects.get(pk=2)
        three = AgendaItem.objects.get(pk=3)
        self.assertEqual(2, one.order)
        self.assertEqual(3, two.order)
        self.assertEqual(1, three.order)
