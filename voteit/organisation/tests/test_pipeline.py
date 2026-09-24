from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from social_core.exceptions import AuthException
from django.utils.timezone import now
from social_django.models import UserSocialAuth

from voteit.app.scouterna import SCOUTID_PROVIDER
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import GlobalTermsOfService
from voteit.organisation.models import Organisation
from voteit.organisation.models import UserAccept
from voteit.organisation.pipeline import _transfer_social_auths
from voteit.organisation.pipeline import CONNECT_INTENT_SESSION_KEY
from voteit.organisation.pipeline import ACCEPT_TOS_FIELD
from voteit.organisation.pipeline import ensure_userid
from voteit.organisation.pipeline import inherit_users
from voteit.organisation.pipeline import LINK_ACCOUNT_FIELD
from voteit.organisation.pipeline import LINK_ACCOUNT_NEW
from voteit.organisation.pipeline import match_existing_user
from voteit.organisation.pipeline import require_connect_intent
from voteit.organisation.pipeline import require_tos_accept
from voteit.organisation.pipeline import store_tos_accept
from voteit.organisation.pipeline import social_user
from voteit.organisation.roles import ROLE_ORG_MANAGER
from voteit.organisation.utils import accept_tos

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


class RequireConnectIntentTests(TestCase):
    """
    A signed-in account only picks up a new login method on purpose.
    """

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def _make_backend(self, session=None, social=None):
        backend = MagicMock()
        backend.name = SCOUTID_PROVIDER
        backend.organisation = self.org
        backend.strategy.session_pop.return_value = session
        backend.strategy.storage.user.get_social_auth.return_value = social
        return backend

    def test_anonymous_visitor_is_untouched(self):
        self.assertIsNone(require_connect_intent(self._make_backend(), "a-sub"))

    def test_a_known_credential_is_social_users_business(self):
        user = self.org.users.create(username="kim")
        social = user.social_auth.create(
            provider=SCOUTID_PROVIDER, uid="a-sub", extra_data={}
        )
        backend = self._make_backend(social=social)
        self.assertIsNone(require_connect_intent(backend, "a-sub", user=user))

    def test_intent_lets_the_connection_through(self):
        user = self.org.users.create(username="kim")
        backend = self._make_backend(session=SCOUTID_PROVIDER)
        self.assertIsNone(require_connect_intent(backend, "a-sub", user=user))

    def test_an_unasked_for_credential_drops_the_session_user(self):
        user = self.org.users.create(username="kim")
        backend = self._make_backend()
        self.assertEqual(
            {"user": None}, require_connect_intent(backend, "a-sub", user=user)
        )

    def test_intent_for_another_provider_does_not_count(self):
        user = self.org.users.create(username="kim")
        backend = self._make_backend(session=IDPROXY_PROVIDER)
        self.assertEqual(
            {"user": None}, require_connect_intent(backend, "a-sub", user=user)
        )

    def test_the_intent_is_always_consumed(self):
        """
        A flag left behind could wave through some later login nobody asked for.
        """
        backend = self._make_backend(session=SCOUTID_PROVIDER)
        require_connect_intent(backend, "a-sub")
        backend.strategy.session_pop.assert_called_once_with(CONNECT_INTENT_SESSION_KEY)


class MatchExistingUserTests(TestCase):
    """
    The one decision that hands somebody an account they did not create.

    Everything it will not decide alone pauses the pipeline instead, so nothing
    is created while the question is open.
    """

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def _make_backend(self, email="kim@example.com"):
        backend = MagicMock()
        backend.name = SCOUTID_PROVIDER
        backend.organisation = self.org
        backend.get_verified_email.return_value = email
        return backend

    def _details(self, first="Kim", last="Scout"):
        return {"first_name": first, "last_name": last}

    def _existing(self, **kwargs):
        kwargs.setdefault("username", "kim")
        kwargs.setdefault("first_name", "Kim")
        kwargs.setdefault("last_name", "Scout")
        kwargs.setdefault("email", "kim@example.com")
        kwargs.setdefault("last_login", now())
        return self.org.users.create(**kwargs)

    def _run(self, backend=None, details=None, answer=None, **kwargs):
        self.strategy = MagicMock()
        self.strategy.storage.partial.prepare.return_value.token = "a-token"
        self.strategy.request_data.return_value = (
            {LINK_ACCOUNT_FIELD: answer} if answer else {}
        )
        return match_existing_user(
            strategy=self.strategy,
            backend=backend or self._make_backend(),
            details=details or self._details(),
            pipeline_index=0,
            **kwargs,
        )

    def _asked(self) -> str:
        """Where the paused pipeline sent them to answer."""
        self.strategy.redirect.assert_called_once()
        # Pausing also stores the partial, which is what lets them come back.
        self.strategy.storage.partial.store.assert_called_once()
        return self.strategy.redirect.call_args.args[0]

    def test_an_exact_match_is_linked(self):
        existing = self._existing()
        self.assertEqual({"user": existing, "matched_existing": True}, self._run())
        self.strategy.redirect.assert_not_called()

    def test_case_and_spaces_are_not_differences(self):
        existing = self._existing(email=" Kim@Example.com ", first_name="kim ")
        self.assertEqual(
            existing, self._run(details=self._details(first=" KIM"))["user"]
        )

    def test_nothing_on_the_address_just_carries_on(self):
        self.assertEqual({}, self._run())

    def test_an_unverified_email_matches_nothing(self):
        self._existing()
        self.assertEqual({}, self._run(backend=self._make_backend(email=None)))

    def test_an_inactive_account_is_not_a_match(self):
        self._existing(is_active=False)
        self.assertEqual({}, self._run())

    def test_someone_already_holding_this_provider_is_not_a_match(self):
        existing = self._existing()
        existing.social_auth.create(
            provider=SCOUTID_PROVIDER, uid="another-sub", extra_data={}
        )
        self.assertEqual({}, self._run())

    def test_an_already_resolved_login_is_left_alone(self):
        self._existing()
        other = self.org.users.create(username="someone-else")
        self.assertEqual({}, self._run(user=other))

    def test_the_same_address_under_another_name_asks(self):
        """
        One surname here, both of them there, is one person often enough that
        refusing outright would strand the commonest case there is.
        """
        self._existing()
        paused = self._run(details=self._details(last="Scout Fieldsson"))
        self.assertNotIsInstance(paused, dict)
        self.assertIn("partial_token=a-token", self._asked())

    def test_half_a_name_asks(self):
        self._existing(last_name="")
        paused = self._run(details=self._details(last=""))
        self.assertNotIsInstance(paused, dict)
        self.assertIn("partial_token=a-token", self._asked())

    def test_two_matches_ask_rather_than_guess(self):
        self._existing(username="kim")
        self._existing(username="kim-again")
        paused = self._run()
        self.assertNotIsInstance(paused, dict)
        self.assertIn("partial_token=a-token", self._asked())

    def test_an_account_nobody_ever_used_asks(self):
        """
        Nobody has proved it is theirs -- including the person in front of us.
        """
        self._existing(last_login=None)
        paused = self._run()
        self.assertNotIsInstance(paused, dict)
        self.assertIn("partial_token=a-token", self._asked())

    def test_a_namesake_does_not_stop_the_match(self):
        exact = self._existing(username="kim")
        self._existing(username="sam", first_name="Sam")
        self.assertEqual(exact, self._run()["user"])

    def test_an_elevated_match_blocks_the_login(self):
        """
        A second account for a manager is a merge waiting to happen. Refusing
        keeps them on the one path that proves both logins are theirs.
        """
        existing = self._existing()
        existing.social_auth.create(
            provider=IDPROXY_PROVIDER, uid="an-identity", extra_data={}
        )
        self.org.add_roles(existing, ROLE_ORG_MANAGER)
        with self.assertRaises(AuthException) as caught:
            self._run()
        # Named, because "sign in the way you usually do" is no help to
        # somebody who has just been told no.
        self.assertIn("VoteIT ID", str(caught.exception))

    def test_staff_blocks_the_login_too(self):
        self._existing(is_staff=True)
        with self.assertRaises(AuthException):
            self._run()

    def test_an_elevated_account_with_no_way_in_says_so(self):
        """
        Matched, refused, and nothing they can do from here -- so do not tell
        them to go and sign in with something.
        """
        existing = self._existing()
        self.org.add_roles(existing, ROLE_ORG_MANAGER)
        with self.assertRaises(AuthException) as caught:
            self._run()
        self.assertIn("no way to sign in", str(caught.exception))

    def test_an_elevated_account_under_another_name_is_simply_not_offered(self):
        """
        Somebody else who happens to read the same mailbox. Not this person's
        to claim, and no reason to stop them either.
        """
        boss = self._existing(username="boss", first_name="Sam")
        self.org.add_roles(boss, ROLE_ORG_MANAGER)
        self.assertEqual({}, self._run())
        self.strategy.redirect.assert_not_called()

    def test_answering_with_an_account_links_it(self):
        existing = self._existing(last_login=None)
        self.assertEqual(
            {"user": existing, "matched_existing": True},
            self._run(answer=str(existing.pk)),
        )

    def test_answering_new_carries_on_to_a_fresh_account(self):
        self._existing(last_login=None)
        self.assertEqual({}, self._run(answer=LINK_ACCOUNT_NEW))
        self.strategy.redirect.assert_not_called()

    def test_an_account_that_was_never_on_offer_is_refused(self):
        """
        The pk arrives from the browser, so it only counts if it is still one
        of the accounts this login could have claimed.
        """
        self._existing(last_login=None)
        stranger = self.org.users.create(username="stranger")
        paused = self._run(answer=str(stranger.pk))
        self.assertNotIsInstance(paused, dict)
        self.assertIn("partial_token=a-token", self._asked())

    def test_an_elevated_account_cannot_be_answered_with(self):
        self._existing(last_login=None)
        boss = self._existing(username="boss", first_name="Sam")
        self.org.add_roles(boss, ROLE_ORG_MANAGER)
        paused = self._run(answer=str(boss.pk))
        self.assertNotIsInstance(paused, dict)
        self.assertIn("partial_token=a-token", self._asked())


class RequireTosAcceptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.user = cls.org.users.create(username="kim")
        cls.gtos = GlobalTermsOfService.objects.create()

    def _run(self, user=None, answer=None):
        self.strategy = MagicMock()
        self.strategy.storage.partial.prepare.return_value.token = "a-token"
        self.strategy.request_data.return_value = (
            {ACCEPT_TOS_FIELD: str(answer)} if answer else {}
        )
        backend = MagicMock()
        backend.name = SCOUTID_PROVIDER
        backend.organisation = self.org
        return require_tos_accept(
            strategy=self.strategy, backend=backend, pipeline_index=0, user=user
        )

    def _asked(self) -> str:
        self.strategy.redirect.assert_called_once()
        self.strategy.storage.partial.store.assert_called_once()
        return self.strategy.redirect.call_args.args[0]

    def test_no_tos(self):
        self.assertEqual({}, self._run())
        self.assertEqual({}, self._run(self.user))

    def test_new_user_pauses(self):
        self.org.tos.create(based_on=self.gtos)
        self._run()
        self.assertEqual(
            "/accept-tos?partial_token=a-token&resume_url=%2Fcomplete%2Fscoutid%2F",
            self._asked(),
        )

    def test_new_user_accepts(self):
        tos = self.org.tos.create(based_on=self.gtos)
        self.assertEqual({"accepted_tos": tos.pk}, self._run(answer=tos.pk))
        self.strategy.redirect.assert_not_called()
        # Nothing stored until there's a user
        self.assertFalse(UserAccept.objects.exists())

    def test_accepting_old_version_asks_again(self):
        old = self.org.tos.create(based_on=self.gtos, version=now() - timedelta(days=1))
        self.org.tos.create(based_on=self.gtos)
        self._run(answer=old.pk)
        self._asked()

    def test_existing_user_accepted(self):
        tos = self.org.tos.create(based_on=self.gtos)
        accept_tos(self.user, tos)
        self.assertEqual({}, self._run(self.user))

    def test_existing_user_accepted_older_version(self):
        old = self.org.tos.create(based_on=self.gtos, version=now() - timedelta(days=1))
        accept_tos(self.user, old)
        tos = self.org.tos.create(based_on=self.gtos)
        self._run(self.user)
        self._asked()
        self.assertEqual({"accepted_tos": tos.pk}, self._run(self.user, answer=tos.pk))

    def test_future_version_not_required_yet(self):
        tos = self.org.tos.create(based_on=self.gtos, version=now() - timedelta(days=1))
        accept_tos(self.user, tos)
        self.org.tos.create(based_on=self.gtos, version=now() + timedelta(days=1))
        self.assertEqual({}, self._run(self.user))


class StoreTosAcceptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.user = cls.org.users.create(username="kim")
        cls.tos = cls.org.tos.create(based_on=GlobalTermsOfService.objects.create())

    def test_stores(self):
        store_tos_accept(user=self.user, accepted_tos=self.tos.pk)
        self.assertEqual(self.tos, UserAccept.objects.get(user=self.user).tos)

    def test_nothing_accepted(self):
        store_tos_accept(user=self.user)
        self.assertFalse(UserAccept.objects.exists())
