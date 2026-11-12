from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.timezone import now
from rest_framework.test import APITestCase

from voteit.core.removal import postpone_removal
from voteit.core.testing import IsolatedCacheMixin
from voteit.organisation.models import Organisation

User = get_user_model()


@override_settings(REMOVAL_WAIT_HOURS=3)
class RemovalRequestsTests(IsolatedCacheMixin, APITestCase):
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
                    "vote_transfers": 0,
                    "reactions": 0,
                }
            ],
            participant["meetings"],
        )
        # Too early
        self.assertFalse(moderator["can_remove"])

    def test_list_queries_dont_grow_with_requests(self):
        self.client.force_login(self.org_manager)
        url = reverse("removal-requests-list")
        with CaptureQueriesContext(connection) as before:
            self.client.get(url)
        for i in range(3):
            self.org_manager.organisation.users.create(
                username=f"leaving{i}", removal_requested=now()
            )
        with CaptureQueriesContext(connection) as after:
            response = self.client.get(url)
        self.assertEqual(5, len(response.json()))
        self.assertEqual(len(before), len(after))

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

    def _remove(self, user):
        with (
            patch("voteit.core.sessions.end_tracked_sessions"),
            patch("voteit.messaging.close.close_user_connections"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            return self.client.post(
                reverse("removal-requests-remove", kwargs={"pk": user.pk})
            )

    def test_remove_anonymises_active_user(self):
        self.client.force_login(self.org_manager)
        response = self._remove(self.participant)
        self.assertEqual(200, response.status_code)
        self.assertEqual({"result": "anonymised"}, response.json())
        self.participant.refresh_from_db()
        self.assertIsNotNone(self.participant.anonymised)
        self.assertEqual("", self.participant.email)
        # Confirmation went to the address it had
        self.assertEqual(["participant@voteit.se"], mail.outbox[0].to)
        # Done with, so off the list
        response = self.client.get(reverse("removal-requests-list"))
        self.assertEqual(
            [self.moderator.pk], [item["user"]["pk"] for item in response.json()]
        )

    def test_remove_deletes_user_without_activity(self):
        user = Organisation.objects.get(pk=1).users.create(
            username="nobody",
            email="nobody@voteit.se",
            removal_requested=now() - timedelta(hours=4),
        )
        self.client.force_login(self.org_manager)
        response = self._remove(user)
        self.assertEqual({"result": "deleted"}, response.json())
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertEqual(["nobody@voteit.se"], mail.outbox[0].to)

    def test_remove_confirms_in_organisation_language(self):
        Organisation.objects.filter(pk=1).update(default_language="sv")
        self.client.force_login(self.org_manager)
        with patch("voteit.core.removal.send_removal_confirmation") as confirm:
            self._remove(self.participant)
        confirm.assert_called_once()
        self.assertEqual("participant@voteit.se", confirm.call_args.args[0])
        self.assertEqual("sv", confirm.call_args.args[2])

    def test_remove_too_early(self):
        self.client.force_login(self.org_manager)
        response = self._remove(self.moderator)
        self.assertEqual(400, response.status_code)
        self.moderator.refresh_from_db()
        self.assertIsNone(self.moderator.anonymised)
        self.assertEqual([], mail.outbox)

    def test_remove_self(self):
        self.org_manager.removal_requested = now() - timedelta(days=1)
        self.org_manager.save()
        self.client.force_login(self.org_manager)
        response = self._remove(self.org_manager)
        self.assertEqual(403, response.status_code)
        self.org_manager.refresh_from_db()
        self.assertIsNone(self.org_manager.anonymised)

    def test_remove_without_request(self):
        self.participant.removal_requested = None
        self.participant.save()
        self.client.force_login(self.org_manager)
        self.assertEqual(404, self._remove(self.participant).status_code)

    def test_remove_other_organisation(self):
        self.client.force_login(self.org_manager)
        other = User.objects.get(username="elsewhere")
        self.assertEqual(404, self._remove(other).status_code)

    def test_remove_not_manager(self):
        self.client.force_login(self.moderator)
        self.assertEqual(403, self._remove(self.participant).status_code)

    def _postpone_url(self, user):
        return reverse("removal-requests-postpone", kwargs={"pk": user.pk})

    def test_postpone(self):
        self.client.force_login(self.org_manager)
        until = now() + timedelta(days=2)
        response = self.client.post(
            self._postpone_url(self.participant),
            {"kind": "block", "until": until.isoformat()},
            format="json",
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("block", response.json()["postponed"]["kind"])
        response = self.client.get(reverse("removal-requests-list"))
        participant, moderator = response.json()
        self.assertEqual("block", participant["postponed"]["kind"])
        self.assertIsNone(moderator["postponed"])
        # Advisory only
        self.assertTrue(participant["can_remove"])
        self.assertEqual(200, self._remove(self.participant).status_code)

    def test_postpone_replaces_and_clears(self):
        postpone_removal(self.participant.pk, "block", now() + timedelta(days=1))
        self.client.force_login(self.org_manager)
        url = self._postpone_url(self.participant)
        response = self.client.post(
            url,
            {"kind": "remind", "until": (now() + timedelta(days=1)).isoformat()},
            format="json",
        )
        self.assertEqual("remind", response.json()["postponed"]["kind"])
        response = self.client.delete(url)
        self.assertEqual(200, response.status_code)
        self.assertIsNone(response.json()["postponed"])

    def test_postpone_invalid(self):
        self.client.force_login(self.org_manager)
        url = self._postpone_url(self.participant)
        past = (now() - timedelta(minutes=1)).isoformat()
        future = (now() + timedelta(days=1)).isoformat()
        for data in (
            {"kind": "block", "until": past},
            {"kind": "nope", "until": future},
            {"kind": "block"},
        ):
            with self.subTest(data=data):
                response = self.client.post(url, data, format="json")
                self.assertEqual(400, response.status_code)

    def test_postpone_not_manager(self):
        self.client.force_login(self.moderator)
        response = self.client.delete(self._postpone_url(self.participant))
        self.assertEqual(403, response.status_code)

    def test_postpone_other_organisation(self):
        self.client.force_login(self.org_manager)
        other = User.objects.get(username="elsewhere")
        self.assertEqual(404, self.client.delete(self._postpone_url(other)).status_code)
