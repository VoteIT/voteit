from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import Organisation
from voteit.organisation.utils import get_idproxy_user_data

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

    def test_get_idproxy_user_data(self):
        self.assertEqual({"email": {"a@hi.se"}}, get_idproxy_user_data(self.user))
        self.assertEqual(
            {"email": {"a@hi.se"}}, get_idproxy_user_data(self.duplicate_user)
        )

    def test_get_idproxy_user_data_several_items(self):
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
            get_idproxy_user_data(self.user),
        )
        self.assertEqual(
            {"email": {"a@hi.se", "b@hi.se"}, "swedish_ssn": {"121212-1212"}},
            get_idproxy_user_data(self.duplicate_user),
        )
