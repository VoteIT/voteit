from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from rest_framework.test import APITestCase

from voteit.organisation.models import Organisation

User = get_user_model()


@override_settings(REMOVAL_WAIT_HOURS=3)
class RemovalRequestsTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org_manager = User.objects.get(username="org_manager")
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant.removal_requested = now() - timedelta(hours=4)
        cls.participant.save()
        cls.moderator.removal_requested = now()
        cls.moderator.save()
        other_org = Organisation.objects.create(host="other")
        other_org.users.create(username="elsewhere", removal_requested=now())

    def test_list(self):
        self.client.force_login(self.org_manager)
        response = self.client.get(reverse("removal-requests-list"))
        self.assertEqual(200, response.status_code)
        data = response.json()
        # Oldest request first, other organisations left out
        self.assertEqual(
            [self.participant.pk, self.moderator.pk],
            [item["user"]["pk"] for item in data],
        )
        participant, moderator = data
        self.assertTrue(participant["can_remove"])
        self.assertEqual("active_meeting", participant["classification"])
        self.assertEqual(
            [
                {
                    "pk": 1,
                    "title": "Testfixture meeting",
                    "state": "upcoming",
                    "roles": ["pa"],
                    "used_invite": False,
                    "groups": [],
                    "ongoing_polls": 0,
                    "votes": 0,
                    "speaker_entries": 0,
                    "proposals": 0,
                    "discussion_posts": 0,
                }
            ],
            participant["meetings"],
        )
        # Too early
        self.assertFalse(moderator["can_remove"])

    def test_retrieve(self):
        self.client.force_login(self.org_manager)
        response = self.client.get(
            reverse("removal-requests-detail", kwargs={"pk": self.participant.pk})
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(self.participant.pk, response.json()["user"]["pk"])

    def test_retrieve_without_request(self):
        self.client.force_login(self.org_manager)
        response = self.client.get(
            reverse("removal-requests-detail", kwargs={"pk": self.org_manager.pk})
        )
        self.assertEqual(404, response.status_code)

    def test_manager_cant_remove_self(self):
        self.org_manager.removal_requested = now() - timedelta(days=1)
        self.org_manager.save()
        self.client.force_login(self.org_manager)
        response = self.client.get(
            reverse("removal-requests-detail", kwargs={"pk": self.org_manager.pk})
        )
        self.assertFalse(response.json()["can_remove"])

    def test_not_manager(self):
        self.client.force_login(self.moderator)
        response = self.client.get(reverse("removal-requests-list"))
        self.assertEqual(403, response.status_code)

    def test_anonymous(self):
        response = self.client.get(reverse("removal-requests-list"))
        self.assertIn(response.status_code, (401, 403))
