from unittest.mock import MagicMock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from social_django.models import UserSocialAuth

from voteit.organisation.models import Organisation
from voteit.organisation.pipeline import ensure_userid
from voteit.organisation.pipeline import social_user

User = get_user_model()


class EnsureUseridTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def _make_user(self, **kwargs):
        return self.org.users.create(**kwargs)

    def test_skips_when_no_user(self):
        ensure_userid(backend=None, user=None)

    def test_skips_when_userid_already_set(self):
        user = self._make_user(username="already", userid="existing-id")
        ensure_userid(backend=None, user=user)
        user.refresh_from_db()
        self.assertEqual("existing-id", user.userid)

    def test_sets_userid_from_name(self):
        user = self._make_user(username="anna", first_name="Anna", last_name="Karlsson")
        self.assertIsNone(user.userid)
        ensure_userid(backend=None, user=user)
        user.refresh_from_db()
        self.assertEqual("anna-karlsson", user.userid)

    def test_deduplicates_userid(self):
        self._make_user(username="taken", userid="anna-karlsson")
        user = self._make_user(
            username="anna2", first_name="Anna", last_name="Karlsson"
        )
        ensure_userid(backend=None, user=user)
        user.refresh_from_db()
        self.assertIsNotNone(user.userid)
        self.assertNotEqual("anna-karlsson", user.userid)
        self.assertTrue(user.userid.startswith("anna-karlsson-"))

    def test_skips_when_name_cannot_be_slugified(self):
        # A user with no name produces an empty slug, so generate returns None
        user = self._make_user(username="noname")
        ensure_userid(backend=None, user=user)
        user.refresh_from_db()
        self.assertIsNone(user.userid)


class SocialUserInactiveTests(TestCase):
    """
    Tests for the inactive-user loop fix in social_user().

    When a UserSocialAuth points to a deactivated account (common after account
    merges), or when an identity_id lookup returns only deactivated accounts,
    the old code would return the inactive user and let PSA's do_complete reject
    them on every login attempt — a persistent loop. The fix prefers active users.
    """

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def _make_user(self, username, identity_id, is_active=True):
        return self.org.users.create(
            username=username, identity_id=identity_id, is_active=is_active
        )

    def _make_backend(self, social=None):
        """Minimal mock backend: name, organisation, and the social auth storage lookup."""
        backend = MagicMock()
        backend.name = "idproxy"
        backend.organisation = self.org
        backend.strategy.storage.user.get_social_auth.return_value = social
        return backend

    def test_social_auth_inactive_moves_to_active_alternative(self):
        """
        When social.user is inactive but an active user with the same identity_id
        exists, the social auth is moved to the active user and that user is returned.
        This prevents the inactive-user rejection loop in PSA's do_complete.
        """
        inactive = self._make_user("inactive", "uid-123", is_active=False)
        active = self._make_user("active", "uid-123")

        social = MagicMock()
        social.user = inactive
        backend = self._make_backend(social=social)

        result = social_user(backend=backend, uid="uid-123", user=None)

        self.assertEqual(active, result["user"])
        self.assertFalse(result["is_new"])
        # Social auth must be updated so subsequent logins go straight to the active user
        self.assertEqual(active, social.user)
        social.save.assert_called_once()

    def test_social_auth_inactive_no_alternative_returns_inactive(self):
        """
        When social.user is inactive and no active alternative exists, the inactive
        user is returned unchanged. PSA's do_complete will handle the rejection
        (intentionally deactivated account — correct behaviour).
        """
        inactive = self._make_user("inactive-only", "uid-456", is_active=False)

        social = MagicMock()
        social.user = inactive
        backend = self._make_backend(social=social)

        result = social_user(backend=backend, uid="uid-456", user=None)

        self.assertEqual(inactive, result["user"])
        self.assertFalse(result["is_new"])
        social.save.assert_not_called()

    def test_identity_id_lookup_ignores_inactive_users(self):
        """
        When no social auth exists, the identity_id fallback must not return an
        inactive user. Before the fix, a deactivated duplicate account could be
        selected and cause the same rejection loop.
        """
        self._make_user("inactive-dup", "uid-789", is_active=False)

        backend = self._make_backend(social=None)

        result = social_user(backend=backend, uid="uid-789", user=None)

        self.assertIsNone(result["user"])
        self.assertTrue(result["is_new"])
        self.assertTrue(result["new_association"])


class SocialAuthTransferTests(TestCase):
    """
    Tests for social auth transfer when pipeline switches between users
    that share the same identity_id (duplicate accounts scenario).
    """

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def _make_user(self, username, identity_id=None, is_active=True):
        return self.org.users.create(
            username=username, identity_id=identity_id, is_active=is_active
        )

    def _make_social_auth(self, user, uid, provider="idproxy"):
        return UserSocialAuth.objects.create(user=user, uid=uid, provider=provider)

    def _make_backend(self, social=None):
        backend = MagicMock()
        backend.name = "idproxy"
        backend.organisation = self.org
        backend.strategy.storage.user.get_social_auth.return_value = social
        return backend

    @patch("voteit.organisation.pipeline._reauth_user")
    def test_elif_transfers_social_auths_from_logged_in_user(self, mock_reauth):
        """
        When the identity_id lookup finds a different user than the one currently
        logged in, the logged-in user's social auths are transferred to the found
        user before switching sessions.
        """
        logged_in = self._make_user("logged-in", identity_id="old-uid")
        target = self._make_user("target", identity_id="new-uid")
        old_social = self._make_social_auth(logged_in, uid="old-uid")

        backend = self._make_backend(social=None)

        social_user(backend=backend, uid="new-uid", user=logged_in)

        old_social.refresh_from_db()
        self.assertEqual(target, old_social.user)
        mock_reauth.assert_called_once_with(backend, target)

    def test_inactive_to_active_transfers_remaining_social_auths(self):
        """
        When the social auth points to an inactive user and an active alternative
        is found, any other social auths on the inactive user are also moved to
        the active user.
        """
        inactive = self._make_user(
            "inactive-extra", identity_id="uid-C", is_active=False
        )
        active = self._make_user("active-extra", identity_id="uid-C")
        extra_social = self._make_social_auth(inactive, uid="uid-old")

        # Mock social auth for the current uid pointing at the inactive user
        current_social = MagicMock()
        current_social.user = inactive
        backend = self._make_backend(social=current_social)

        social_user(backend=backend, uid="uid-C", user=None)

        extra_social.refresh_from_db()
        self.assertEqual(active, extra_social.user)
