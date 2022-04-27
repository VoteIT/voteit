from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup

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
        self.assertEqual(response.status_code, 403)

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


class MeetingGroupViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.anon = User.objects.create(username="anon")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting_group: MeetingGroup = MeetingGroup.objects.create(
            meeting=cls.meeting
        )

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_create(self):
        url = reverse("meeting-groups-list")
        data = {"title": "Hello world", "meeting": self.meeting.pk}

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

    def test_create_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        data = {"title": "Hello world", "meeting": self.meeting.pk}
        url = reverse("meeting-groups-list")
        response = self.client.post(url, data)
        self.assertEqual(403, response.status_code)

    def test_create_no_meeting(self):
        self.client.force_login(self.moderator)
        data = {"title": "Hello world"}
        url = reverse("meeting-groups-list")
        response = self.client.post(url, data)
        self.assertEqual(400, response.status_code)

    def test_get(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.meeting_group.pk, data.get("pk", None))

    def test_get_wrong_user(self):
        self.client.force_login(self.anon)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_list_no_meeting(self):
        url = reverse("meeting-groups-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json())

    def test_list(self):
        url = reverse("meeting-groups-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(self.meeting_group.pk, data[0]["pk"])

    def test_change(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(url, data={"title": "Hello"})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual("Hello", data["title"])

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.patch(url, data={"title": "Hello"})
        self.assertEqual(403, response.status_code)

    def test_delete(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)

    def test_delete_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.client.force_login(self.moderator)
        url = reverse("meeting-groups-detail", kwargs={"pk": self.meeting_group.pk})
        response = self.client.delete(url)
        self.assertEqual(403, response.status_code)
