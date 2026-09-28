from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.app.scouterna import SCOUTID_PROVIDER
from voteit.app.scouterna.backends import SCOUTNET_MEMBER_NO
from voteit.app.scouterna.testing import scoutid_disabled
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import Organisation
from voteit.organisation.utils import get_user_identity_data
from voteit.organisation.utils import get_user_member_ids

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
