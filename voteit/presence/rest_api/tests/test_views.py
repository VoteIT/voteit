from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase


User = get_user_model()


class PresenceSystemTests(APITestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.participant: User = User.objects.create_user("participant")
        self.moderator: User = User.objects.create_user("moderator")
        self.outsider: User = User.objects.create_user("outsider")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)

    def _mk_one(self):
        from voteit.presence.models import PresenceSystem

        return PresenceSystem.objects.create(meeting=self.meeting)

    def test_create(self):
        url = reverse("presence-systems-list")
        data = {"meeting": self.meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            201,
        )
        self.assertIsNotNone(self.meeting.presence_system)

    def test_create_bad_users(self):
        url = reverse("presence-systems-list")
        data = {"meeting": self.meeting.pk}
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

    def test_create_meeting_ne(self):
        url = reverse("presence-systems-list")
        data = {"meeting": -1}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_list(self):
        url = reverse("presence-systems-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_list_w_meeting(self):
        url = reverse("presence-systems-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, {"meeting": self.meeting.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))

    def test_get(self):
        system = self._mk_one()
        url = f"/api/presence-systems/{system.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(system.pk, data["pk"])
        self.assertEqual(self.meeting.pk, data["meeting"])

    def test_patch(self):
        from voteit.meeting.models import Meeting

        system = self._mk_one()
        new_meeting = Meeting.objects.create()
        url = f"/api/presence-systems/{system.pk}/"
        data = {"meeting": new_meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        system.refresh_from_db(fields=("meeting",))
        self.assertEqual(self.meeting, system.meeting)

    def test_delete(self):
        system = self._mk_one()
        url = f"/api/presence-systems/{system.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, system.refresh_from_db)


class PresenceCheckTests(APITestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT
        from voteit.presence.models import PresenceSystem

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.participant: User = User.objects.create_user("participant")
        self.moderator: User = User.objects.create_user("moderator")
        self.outsider: User = User.objects.create_user("outsider")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)
        self.system: PresenceSystem = PresenceSystem.objects.create(
            meeting=self.meeting
        )

    def _mk_one(self):
        from voteit.presence.models import PresenceCheck

        return PresenceCheck.objects.create(meeting=self.meeting)

    def test_create(self):
        url = reverse("presence-checks-list")
        data = {"meeting": self.meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            201,
        )
        self.assertIs(self.meeting.presence_checks.exists(), True)

    def test_create_bad_users(self):
        url = reverse("presence-checks-list")
        data = {"meeting": self.meeting.pk}
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
        url = reverse("presence-checks-list")
        data = {"meeting": -1}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_list(self):
        url = reverse("presence-checks-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_list_w_meeting(self):
        self._mk_one()
        url = reverse("presence-checks-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, {"meeting": self.meeting.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_get(self):
        presence_check = self._mk_one()
        url = f"/api/presence-checks/{presence_check.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(presence_check.pk, data["pk"])
        self.assertEqual(self.meeting.pk, data["meeting"])

    def test_delete(self):
        presence_check = self._mk_one()
        url = f"/api/presence-checks/{presence_check.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, presence_check.refresh_from_db)
