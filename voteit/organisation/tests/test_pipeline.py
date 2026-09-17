from unittest.mock import MagicMock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from social_django.models import UserSocialAuth

from voteit.app.scouterna import SCOUTID_PROVIDER
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import Organisation
from voteit.organisation.pipeline import _transfer_social_auths
from voteit.organisation.pipeline import ensure_userid
from voteit.organisation.pipeline import inherit_users
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


class InheritUsersTests(TestCase):
    """
    identity_id is an id proxy identifier, and only the id proxy writes it.

    It is what ``UserView.alternate`` / ``switch``, ``UserMerger`` and the admin
    duplicate filter group accounts by. Another provider's uid has no place in
    that namespace, so those backends leave the field entirely alone.
    """

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def _make_backend(self, name):
        backend = MagicMock()
        backend.name = name
        backend.organisation = self.org
        return backend

    def test_other_provider_leaves_an_established_identity_alone(self):
        user = self.org.users.create(username="kim", identity_id="an-id-proxy-identity")
        inherit_users(self._make_backend(SCOUTID_PROVIDER), user, {}, "a-keycloak-sub")
        user.refresh_from_db()
        self.assertEqual("an-id-proxy-identity", user.identity_id)

    def test_other_provider_never_writes_an_identity(self):
        """
        Not even into an empty field: the namespace is the id proxy's.
        """
        user = self.org.users.create(username="kim")
        inherit_users(self._make_backend(SCOUTID_PROVIDER), user, {}, "a-keycloak-sub")
        user.refresh_from_db()
        self.assertIsNone(user.identity_id)

    def test_id_proxy_still_rekeys(self):
        """
        The id proxy is authoritative for identities, so it may overwrite.
        """
        user = self.org.users.create(username="kim", identity_id="old")
        inherit_users(self._make_backend(IDPROXY_PROVIDER), user, {}, "new")
        user.refresh_from_db()
        self.assertEqual("new", user.identity_id)

    def test_id_proxy_still_inherits_extra_identities(self):
        user = self.org.users.create(username="kim", identity_id="new")
        duplicate = self.org.users.create(username="kim-again", identity_id="old")
        inherit_users(
            self._make_backend(IDPROXY_PROVIDER),
            user,
            {"extra_identity_ids": ["old"]},
            "new",
        )
        duplicate.refresh_from_db()
        self.assertEqual("new", duplicate.identity_id)

    def test_other_provider_does_not_inherit_extra_identities(self):
        """
        ``extra_identity_ids`` is the id proxy's own re-keying channel.
        """
        user = self.org.users.create(username="kim", identity_id="a-keycloak-sub")
        duplicate = self.org.users.create(username="kim-again", identity_id="old")
        inherit_users(
            self._make_backend(SCOUTID_PROVIDER),
            user,
            {"extra_identity_ids": ["old"]},
            "a-keycloak-sub",
        )
        duplicate.refresh_from_db()
        self.assertEqual("old", duplicate.identity_id)


class TransferSocialAuthsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def test_every_provider_moves_by_default(self):
        """
        ``UserView.switch`` moves the whole person, so leaving a login method
        behind would send the next login straight back to the old row.
        """
        source = self.org.users.create(username="source", identity_id="same")
        target = self.org.users.create(username="target", identity_id="same")
        source.social_auth.create(provider=IDPROXY_PROVIDER, uid="same", extra_data={})
        source.social_auth.create(provider=SCOUTID_PROVIDER, uid="sub", extra_data={})
        _transfer_social_auths(source, target)
        self.assertEqual(0, source.social_auth.count())
        self.assertEqual(
            {IDPROXY_PROVIDER, SCOUTID_PROVIDER},
            set(target.social_auth.values_list("provider", flat=True)),
        )

    def test_a_single_provider_can_still_be_named(self):
        source = self.org.users.create(username="source", identity_id="same")
        target = self.org.users.create(username="target", identity_id="same")
        source.social_auth.create(provider=IDPROXY_PROVIDER, uid="same", extra_data={})
        source.social_auth.create(provider=SCOUTID_PROVIDER, uid="sub", extra_data={})
        _transfer_social_auths(source, target, IDPROXY_PROVIDER)
        self.assertEqual(
            [SCOUTID_PROVIDER],
            list(source.social_auth.values_list("provider", flat=True)),
        )
        self.assertEqual(
            [IDPROXY_PROVIDER],
            list(target.social_auth.values_list("provider", flat=True)),
        )


class SocialUserOtherProviderTests(TestCase):
    """
    A backend that is not the id proxy resolves by credential alone.
    """

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def _make_backend(self, social=None):
        backend = MagicMock()
        backend.name = SCOUTID_PROVIDER
        backend.organisation = self.org
        backend.strategy.storage.user.get_social_auth.return_value = social
        return backend

    def test_matching_identity_id_is_not_adopted(self):
        """
        An id proxy identity that happens to equal another provider's uid is a
        different namespace, not the same person.
        """
        self.org.users.create(username="kim", identity_id="collides")
        result = social_user(self._make_backend(), "collides")
        self.assertIsNone(result["user"])
        self.assertTrue(result["is_new"])

    def test_credential_resolves_its_own_user(self):
        user = self.org.users.create(username="kim")
        social = user.social_auth.create(
            provider=SCOUTID_PROVIDER, uid="a-sub", extra_data={}
        )
        result = social_user(self._make_backend(social), "a-sub")
        self.assertEqual(user, result["user"])
        self.assertFalse(result["is_new"])
        self.assertFalse(result["new_association"])

    def test_logged_in_user_is_kept_for_a_new_credential(self):
        """
        The connect case: someone signed in attaches a second login method.
        """
        user = self.org.users.create(username="kim", identity_id="an-id-proxy-identity")
        result = social_user(self._make_backend(), "a-sub", user=user)
        self.assertEqual(user, result["user"])
        self.assertTrue(result["new_association"])
