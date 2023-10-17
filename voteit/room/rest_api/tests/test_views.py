from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()


class RoomsViewTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create()
        cls.other_meeting: Meeting = Meeting.objects.create()
        # Speaker system
        cls.sls = cls.meeting.speaker_systems.create(method_name="simple")
        # Props
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        # Users
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        # Default room
        cls.room = cls.meeting.rooms.create(title="Room", sls=cls.sls)
        cls.room.highlighted_proposals.create(proposal=cls.prop1)
        cls.room.highlighted_proposals.create(proposal=cls.prop2)

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_create(self):
        url = reverse("rooms-list")
        data = {
            "title": "A big room",
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

    def test_create_duplicate(self):
        url = reverse("rooms-list")
        data = {"title": "A big room", "meeting": self.meeting.pk, "sls": self.sls.pk}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_create_sls_ne(self):
        url = reverse("rooms-list")
        data = {"title": "A big room", "meeting": self.meeting.pk, "sls": -1}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            {"sls": ['Invalid pk "-1" - object does not exist.']}, response.json()
        )

    def test_list(self):
        url = reverse("rooms-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.participant)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_list_anon(self):
        url = reverse("rooms-list")
        data = {
            "meeting": self.meeting.pk,
        }
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 401)

    def test_list_outsider(self):
        url = reverse("rooms-list")
        self.client.force_login(self.outsider)
        data = {
            "meeting": self.meeting.pk,
        }
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([], response.json())

    def test_patch_change_meeting(self):
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        data = {"meeting": self.other_meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.meeting.pk, data["meeting"])

    def test_patch_change_highlighted(self):
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": [self.prop3.pk, self.prop2.pk]}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([self.prop3.pk, self.prop2.pk], data["highlighted"])
        self.assertEqual(
            [self.prop3.pk, self.prop2.pk], list(self.room.highlighted_proposal_pks)
        )

    def test_patch_change_highlighted_order(self):
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": [self.prop1.pk, self.prop2.pk]}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([self.prop1.pk, self.prop2.pk], data["highlighted"])
        self.assertEqual(
            [self.prop1.pk, self.prop2.pk], list(self.room.highlighted_proposal_pks)
        )

    def test_patch_blank_highlighted(self):
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": []}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([], data["highlighted"])
        self.assertEqual([], list(self.room.highlighted_proposal_pks))
