from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import localdate
from django.utils.timezone import now

from voteit.app.scouterna import SCOUTID_PROVIDER
from voteit.app.scouterna.backends import SCOUTNET_MEMBER_NO
from voteit.app.scouterna.testing import scoutid_disabled
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import GlobalTermsOfService
from voteit.organisation.models import Organisation
from voteit.organisation.utils import accept_tos
from voteit.organisation.utils import get_accepted
from voteit.organisation.utils import get_current_tos
from voteit.organisation.utils import get_published_global_tos
from voteit.organisation.utils import get_user_identity_data
from voteit.organisation.utils import get_user_member_ids
from voteit.organisation.utils import has_newer_global_tos

User = get_user_model()


class UtilsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        SAME_UID = "abc"
        cls.user = cls.organisation.users.create(username="user", identity_id=SAME_UID)
        cls.usa = cls.user.social_auth.create(
            provider=IDPROXY_PROVIDER,
            uid=SAME_UID,
            extra_data={
                "access_token": "123",
                "sensitive_data": True,
                "user_data": {"email": ["a@hi.se"]},
            },
        )
        cls.duplicate_user = cls.organisation.users.create(
            username="duplicate", identity_id=SAME_UID
        )

    def test_get_user_identity_data(self):
        self.assertEqual({"email": {"a@hi.se"}}, get_user_identity_data(self.user))
        self.assertEqual(
            {"email": {"a@hi.se"}}, get_user_identity_data(self.duplicate_user)
        )

    def test_get_user_identity_data_several_items(self):
        self.duplicate_user.social_auth.create(
            provider=IDPROXY_PROVIDER,
            uid="abcd",
            extra_data={
                "access_token": "1234",
                "sensitive_data": True,
                "user_data": {
                    "email": ["a@hi.se", "b@hi.se"],
                    "swedish_ssn": ["121212-1212"],
                },
            },
        )
        self.assertEqual(
            {"email": {"a@hi.se", "b@hi.se"}, "swedish_ssn": {"121212-1212"}},
            get_user_identity_data(self.user),
        )
        self.assertEqual(
            {"email": {"a@hi.se", "b@hi.se"}, "swedish_ssn": {"121212-1212"}},
            get_user_identity_data(self.duplicate_user),
        )

    def test_unlinked_users_do_not_share_identity_data(self):
        """
        A null identity_id must not join an account to every other unlinked one.
        """
        orphan = self.organisation.users.create(username="orphan")
        other_orphan = self.organisation.users.create(username="other-orphan")
        other_orphan.social_auth.create(
            provider=IDPROXY_PROVIDER,
            uid="xyz",
            extra_data={"user_data": {"email": ["not-yours@hi.se"]}},
        )
        self.assertEqual({}, get_user_identity_data(orphan))

    def test_data_is_merged_across_providers(self):
        self.user.social_auth.create(
            provider=SCOUTID_PROVIDER,
            uid="a-keycloak-uuid",
            extra_data={
                "user_data": {
                    "email": ["kim@scoutkaren.example"],
                    SCOUTNET_MEMBER_NO: ["9876543"],
                },
            },
        )
        self.assertEqual(
            {
                "email": {"a@hi.se", "kim@scoutkaren.example"},
                SCOUTNET_MEMBER_NO: {"9876543"},
            },
            get_user_identity_data(self.user),
        )

    def test_disabled_backends_contribute_nothing(self):
        """
        voteit ships as a package; a deployment may leave a backend out, and a
        credential for one nobody can log in with vouches for nothing.
        """
        self.user.social_auth.create(
            provider=SCOUTID_PROVIDER,
            uid="a-keycloak-uuid",
            extra_data={"user_data": {"email": ["kim@scoutkaren.example"]}},
        )
        with scoutid_disabled():
            self.assertEqual({"email": {"a@hi.se"}}, get_user_identity_data(self.user))

    def test_providers_limits_the_backends(self):
        self.user.social_auth.create(
            provider=SCOUTID_PROVIDER,
            uid="a-keycloak-uuid",
            extra_data={"user_data": {SCOUTNET_MEMBER_NO: ["9876543"]}},
        )
        self.assertEqual(
            {SCOUTNET_MEMBER_NO: {"9876543"}},
            get_user_identity_data(self.user, providers=[SCOUTID_PROVIDER]),
        )
        self.assertEqual({}, get_user_identity_data(self.user, providers=[]))

    def test_get_user_member_ids(self):
        self.user.social_auth.create(
            provider=SCOUTID_PROVIDER,
            uid="a-keycloak-uuid",
            extra_data={"user_data": {SCOUTNET_MEMBER_NO: ["9876543"]}},
        )
        self.assertEqual({"9876543"}, get_user_member_ids(self.user))
        with scoutid_disabled():
            self.assertEqual(set(), get_user_member_ids(self.user))

    def test_get_user_member_ids_only_reads_the_backends_key(self):
        # The id proxy has no MEMBER_ID_KEY
        self.usa.extra_data["user_data"][SCOUTNET_MEMBER_NO] = ["9876543"]
        self.usa.save()
        self.assertEqual(set(), get_user_member_ids(self.user))


class TermsOfServiceUtilsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.user = cls.org.users.create(username="kim")

    def _global(self, days_ago=0, required_in=None):
        return GlobalTermsOfService.objects.create(
            version=now() - timedelta(days=days_ago),
            required_from=None
            if required_in is None
            else localdate() + timedelta(days=required_in),
        )

    def test_nothing_to_accept(self):
        self.assertIsNone(get_current_tos(self.org).version)
        self.assertIsNone(get_current_tos(None).version)
        self.assertFalse(get_current_tos(self.org, self.user).must_accept)
        self.assertFalse(get_current_tos(self.org).must_accept)

    def test_org_tos(self):
        tos = self.org.tos.create(version=now() - timedelta(days=1))
        self.org.tos.create(version=now() + timedelta(days=1))
        self.assertEqual(tos.version, get_current_tos(self.org).version)

    def test_global_counts_from_required_from(self):
        self.org.tos.create(version=now() - timedelta(days=5))
        self._global(days_ago=2)
        upcoming = self._global(days_ago=1, required_in=1)
        gtos = self._global(days_ago=3, required_in=0)
        self.assertEqual(gtos.version, get_current_tos(self.org).version)
        # Without organisation terms there's nothing to wait for
        self.assertEqual(upcoming.version, get_current_tos(None).version)

    def test_newest_of_both(self):
        gtos = self._global(days_ago=1, required_in=-1)
        self.org.tos.create(version=now() - timedelta(days=2))
        self.assertEqual(gtos.version, get_current_tos(self.org).version)
        tos = self.org.tos.create()
        self.assertEqual(tos.version, get_current_tos(self.org).version)

    def test_published_global_in_effect(self):
        tos = self.org.tos.create(version=now() - timedelta(days=5))
        gtos = self._global(days_ago=3, required_in=0)
        self._global(days_ago=2, required_in=5)
        self._global()
        self.assertEqual(gtos, get_published_global_tos(tos))

    def test_published_global_without_org_tos(self):
        self._global(days_ago=3, required_in=0)
        upcoming = self._global(days_ago=2, required_in=5)
        self._global()
        self.assertEqual(upcoming, get_published_global_tos(None))

    def test_published_global_older_than_org_tos(self):
        self._global(days_ago=3, required_in=-3)
        upcoming = self._global(days_ago=2, required_in=5)
        tos = self.org.tos.create(version=now() - timedelta(days=1))
        self._global(days_ago=0, required_in=5)
        self.assertEqual(upcoming, get_published_global_tos(tos))

    def test_required_global_org_tos_not_active_yet(self):
        self.org.tos.create(version=now() - timedelta(days=5))
        gtos = self._global(days_ago=3, required_in=-3)
        self._global(days_ago=2, required_in=5)
        self.org.tos.create(version=now() + timedelta(days=1))
        self.assertEqual(gtos.version, get_current_tos(self.org).version)

    def test_has_newer_global_tos(self):
        self.assertFalse(has_newer_global_tos(None))
        tos = self.org.tos.create(version=now() - timedelta(days=2))
        self._global(days_ago=3, required_in=-3)
        self.assertFalse(has_newer_global_tos(tos))
        # Drafts don't count
        self._global(days_ago=1)
        self.assertFalse(has_newer_global_tos(tos))
        # Upcoming counts, managers get time to review before it's required
        upcoming = self._global(days_ago=1, required_in=5)
        self.assertTrue(has_newer_global_tos(tos))
        # Already newer, no need to ask
        with self.assertNumQueries(0):
            self.assertTrue(has_newer_global_tos(tos, upcoming))

    def test_must_accept(self):
        self.org.tos.create(version=now() - timedelta(days=1))
        self.assertTrue(get_current_tos(self.org, self.user).must_accept)
        self.assertTrue(get_current_tos(self.org).must_accept)
        accept_tos(self.user)
        self.assertFalse(get_current_tos(self.org, self.user).must_accept)
        self.org.tos.create()
        self.assertTrue(get_current_tos(self.org, self.user).must_accept)

    def test_current_is_lazy(self):
        self.org.tos.create(version=now() - timedelta(days=1))
        with self.assertNumQueries(2):
            current = get_current_tos(self.org, self.user)
        with self.assertNumQueries(1):
            self.assertTrue(current.must_accept)
            self.assertIsNone(current.accepted)
        current = get_current_tos(self.org)
        with self.assertNumQueries(0):
            self.assertIsNone(current.accepted)

    def test_accept_replaces_previous(self):
        first = accept_tos(self.user)
        second = accept_tos(self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.accepted, get_accepted(self.user))
