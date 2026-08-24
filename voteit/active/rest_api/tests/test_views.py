from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils.timezone import now
from voteit.messaging.testing import testing_channel_layers_setting
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.active.components import ActiveUsersComponent
from voteit.messaging.models import Connection
from voteit.active.messages import ActiveUserChanged
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.statemachines import MeetingStateMachine

User = get_user_model()


class ActiveUserViewSetBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.create_user("participant")
        cls.moderator = User.objects.create_user("moderator")
        cls.outsider = User.objects.create_user("outsider")
        cls.meeting: Meeting = Meeting.objects.create(
            state=MeetingStateMachine.ongoing.value
        )
        cls.component = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)


class ActiveUserListTests(ActiveUserViewSetBase):
    def test_list_returns_empty(self):
        url = reverse("active-users-list")
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json())

    def test_list_unauthenticated(self):
        url = reverse("active-users-list")
        response = self.client.get(url)
        self.assertEqual(401, response.status_code)


class ActiveActionTests(ActiveUserViewSetBase):
    def test_set_active_creates_and_returns_201(self):
        url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, {"active": True})
        self.assertEqual(201, response.status_code)
        self.assertTrue(
            self.meeting.active_users.filter(user=self.participant).exists()
        )

    def test_set_active_already_exists_returns_200(self):
        self.meeting.active_users.create(user=self.participant)
        url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, {"active": True})
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            1, self.meeting.active_users.filter(user=self.participant).count()
        )

    def test_set_inactive_deletes_and_returns_204(self):
        self.meeting.active_users.create(user=self.participant)
        url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, {"active": False})
        self.assertEqual(204, response.status_code)
        self.assertFalse(
            self.meeting.active_users.filter(user=self.participant).exists()
        )

    def test_set_inactive_when_not_active_returns_204(self):
        url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, {"active": False})
        self.assertEqual(204, response.status_code)

    def test_outsider_gets_404(self):
        url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.outsider)
        response = self.client.post(url, {"active": True})
        self.assertEqual(404, response.status_code)

    def test_unauthenticated_gets_401(self):
        url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
        response = self.client.post(url, {"active": True})
        self.assertEqual(401, response.status_code)

    def test_component_disabled_gets_404(self):
        self.component.enabled = False
        self.component.save()
        try:
            url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
            self.client.force_login(self.participant)
            response = self.client.post(url, {"active": True})
            self.assertEqual(404, response.status_code)
        finally:
            self.component.enabled = True
            self.component.save()


class PurgeActionTests(ActiveUserViewSetBase):
    def _setup_active_and_connections(self):
        self.meeting.active_users.create(user=self.moderator)
        active_participant = self.meeting.active_users.create(user=self.participant)
        Connection.objects.create(user_id=self.moderator.pk, last_action=now())
        Connection.objects.create(
            user_id=self.participant.pk, last_action=now() - timedelta(days=1)
        )
        return active_participant

    def test_purge_removes_inactive_and_returns_count(self):
        self._setup_active_and_connections()
        url = reverse("active-users-purge", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"hours": 1})
        self.assertEqual(200, response.status_code)
        self.assertEqual({"count": 1}, response.json())
        self.assertFalse(
            self.meeting.active_users.filter(user=self.participant).exists()
        )
        self.assertTrue(self.meeting.active_users.filter(user=self.moderator).exists())

    def test_purge_with_high_hours_removes_nothing(self):
        self._setup_active_and_connections()
        url = reverse("active-users-purge", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"hours": 48})
        self.assertEqual(200, response.status_code)
        self.assertEqual({"count": 0}, response.json())
        self.assertEqual(2, self.meeting.active_users.count())

    def test_purge_with_hours_zero_uses_5_min_cutoff(self):
        self.meeting.active_users.create(user=self.moderator)
        self.meeting.active_users.create(user=self.participant)
        Connection.objects.create(user_id=self.moderator.pk, last_action=now())
        Connection.objects.create(user_id=self.participant.pk, last_action=now())
        url = reverse("active-users-purge", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, {"hours": 0})
        self.assertEqual(200, response.status_code)
        self.assertEqual({"count": 0}, response.json())

    def test_purge_participant_gets_403(self):
        url = reverse("active-users-purge", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, {"hours": 1})
        self.assertEqual(403, response.status_code)

    def test_purge_outsider_gets_404(self):
        url = reverse("active-users-purge", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.outsider)
        response = self.client.post(url, {"hours": 1})
        self.assertEqual(404, response.status_code)

    def test_purge_unauthenticated_gets_401(self):
        url = reverse("active-users-purge", kwargs={"pk": self.meeting.pk})
        response = self.client.post(url, {"hours": 1})
        self.assertEqual(401, response.status_code)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class ActiveActionMessageTests(ActiveUserViewSetBase):
    """Verify that ActiveUserChanged is published when the REST endpoint changes active state."""

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_set_active_publishes_active_user_changed(self, mock_publish):
        url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        self.client.post(url, {"active": True})
        self.assertTrue(mock_publish.called)
        msg = mock_publish.call_args.args[0]
        self.assertIsInstance(msg, ActiveUserChanged)
        self.assertEqual(msg.payload.user, self.participant.pk)
        self.assertEqual(msg.payload.meeting, self.meeting.pk)
        self.assertTrue(msg.payload.active)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_set_inactive_publishes_active_user_changed(self, mock_publish):
        self.meeting.active_users.create(user=self.participant)
        url = reverse("active-users-active", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {"active": False})
        self.assertTrue(mock_publish.called)
        msg = mock_publish.call_args.args[0]
        self.assertIsInstance(msg, ActiveUserChanged)
        self.assertEqual(msg.payload.user, self.participant.pk)
        self.assertEqual(msg.payload.meeting, self.meeting.pk)
        self.assertFalse(msg.payload.active)
