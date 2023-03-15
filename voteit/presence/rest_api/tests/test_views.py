from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.presence.components import PresenceCheckComponent

User = get_user_model()


class PresenceCheckTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.component = cls.meeting.components.create(
            component_name=PresenceCheckComponent.name, state=EnabledWf.ON
        )
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

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

    def test_create_component_disabled(self):
        self.component.delete()
        url = reverse("presence-checks-list")
        data = {"meeting": self.meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            403,
        )

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
        self.assertEqual(response.status_code, 200)
        self.assertEqual([], response.json())

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


class PresenceTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT
        from voteit.presence.models import PresenceCheck

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        # cls.system: PresenceSystem = PresenceSystem.objects.create(meeting=cls.meeting)
        cls.check: PresenceCheck = cls.meeting.presence_checks.create()
        cls.present_moderator = cls.check.presences.create(user=cls.moderator)
        cls.present_participant = cls.check.presences.create(user=cls.participant)

    def test_create(self):
        url = reverse("presences-list")
        data = {"presence_check": self.check.pk}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            405,
        )

    def test_list_wo_context(self):
        url = reverse("presences-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([], response.json())

    def test_list(self):
        url = reverse("presences-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, {"presence_check": self.check.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [self.present_moderator.pk, self.present_participant.pk],
            sorted(x["pk"] for x in response.json()),
        )

    def test_get(self):
        self.client.force_login(self.moderator)
        url = reverse("presences-detail", kwargs={"pk": self.present_moderator.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.present_moderator.pk, data["pk"])

    def test_delete(self):
        self.client.force_login(self.moderator)
        url = reverse("presences-detail", kwargs={"pk": self.present_moderator.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 405)

    def test_put(self):
        self.client.force_login(self.moderator)
        url = reverse("presences-detail", kwargs={"pk": self.present_moderator.pk})
        response = self.client.put(url, {})
        self.assertEqual(response.status_code, 405)
