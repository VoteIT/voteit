from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from voteit.messaging.testing import testing_channel_layers_setting
from social_django.models import UserSocialAuth

from voteit.meeting.models import Meeting
from voteit.organisation.models import Organisation

User = get_user_model()


def _mk_org():
    return Organisation.objects.create()


def _mk_user(org, username, **kwargs):
    return User.objects.create(username=username, organisation=org, **kwargs)


def _mk_meeting(org):
    return Meeting.objects.create(organisation=org)


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
    ENVELOPE_CONNECTIONS_QUEUE=None,
)
class DeactivateUnusedUsersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = _mk_org()
        cls.meeting = _mk_meeting(cls.org)

    @staticmethod
    def _run():
        from voteit.core.jobs import deactivate_unused_users

        return deactivate_unused_users()

    def _old_user(self, username):
        user = _mk_user(self.org, username)
        user.last_login = now() - timedelta(days=31)
        user.save(update_fields=["last_login"])
        return user

    def test_old_login_no_roles_deactivated(self):
        user = self._old_user("old_no_roles")
        count = self._run()
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(1, count)

    def test_old_login_with_meeting_roles_skipped(self):
        from voteit.meeting.roles import ROLE_PARTICIPANT

        user = self._old_user("old_meeting_roles")
        self.meeting.add_roles(user, ROLE_PARTICIPANT)
        count = self._run()
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(0, count)

    def test_old_login_with_organisation_roles_skipped(self):
        from voteit.organisation.roles import ROLE_ORG_MANAGER

        user = self._old_user("old_org_roles")
        self.org.add_roles(user, ROLE_ORG_MANAGER)
        count = self._run()
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(0, count)

    def test_recent_login_no_roles_not_deactivated(self):
        user = _mk_user(self.org, "recent_login")
        user.last_login = now() - timedelta(days=5)
        user.save(update_fields=["last_login"])
        count = self._run()
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(0, count)

    def test_null_last_login_no_roles_deactivated(self):
        user = _mk_user(self.org, "never_logged_in")
        self.assertIsNone(user.last_login)
        count = self._run()
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(1, count)

    def test_already_inactive_not_counted(self):
        user = _mk_user(self.org, "already_inactive")
        user.last_login = now() - timedelta(days=31)
        user.is_active = False
        user.save(update_fields=["last_login", "is_active"])
        count = self._run()
        self.assertEqual(0, count)

    def test_social_auth_cleared_on_deactivation(self):
        user = self._old_user("social_auth_user")
        UserSocialAuth.objects.create(
            user=user, provider="testprovider", uid="test-uid"
        )
        self._run()
        self.assertFalse(UserSocialAuth.objects.filter(user=user).exists())

    def test_social_auth_kept_for_active_user(self):
        user = _mk_user(self.org, "active_social")
        user.last_login = now() - timedelta(days=5)
        user.save(update_fields=["last_login"])
        UserSocialAuth.objects.create(
            user=user, provider="testprovider", uid="test-uid-2"
        )
        self._run()
        self.assertTrue(UserSocialAuth.objects.filter(user=user).exists())
