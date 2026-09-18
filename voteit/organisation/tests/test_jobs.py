from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from voteit.messaging.testing import testing_channel_layers_setting
from social_django.models import Code
from social_django.models import Partial
from social_django.models import UserSocialAuth

from voteit.app.scouterna import SCOUTID_PROVIDER
from voteit.app.scouterna.testing import scoutid_enabled
from voteit.core.testing import FakeCommit
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.jobs import cleanup_extra_data_for_older_users
from voteit.organisation.jobs import cleanup_social_auth_leftovers
from voteit.organisation.jobs import email_login_method_added
from voteit.organisation.models import Organisation


User = get_user_model()

#: Patch where the signal imported it, not where it is defined.
SIGNALS = "voteit.organisation.signals"


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class JobsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.usa = UserSocialAuth.objects.get(pk=1)
        cls.usa2 = UserSocialAuth.objects.create(
            user_id=1, extra_data={"email": "mine@betahaus.net"}, uid="abcdefg"
        )

    def test_cleanup_extra_data(self):
        self.assertEqual({"hello": "world"}, self.usa.extra_data)
        cleanup_extra_data_for_older_users()
        self.usa.refresh_from_db()
        self.usa2.refresh_from_db()
        self.assertEqual({}, self.usa.extra_data)
        self.assertEqual({"email": "mine@betahaus.net"}, self.usa2.extra_data)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class LoginMethodAddedTests(TestCase):
    """
    Someone gaining a second way into their account hears about it.
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.user = cls.org.users.create(
            username="kim", first_name="Kim", email="kim@example.com"
        )

    def _social(self, provider, uid):
        with FakeCommit():
            return self.user.social_auth.create(
                provider=provider, uid=uid, extra_data={}
            )

    @patch(f"{SIGNALS}.email_login_method_added")
    def test_a_first_credential_is_a_registration(self, mocked):
        self._social(IDPROXY_PROVIDER, "an-identity")
        mocked.delay.assert_not_called()

    @patch(f"{SIGNALS}.email_login_method_added")
    def test_a_second_credential_notifies(self, mocked):
        self._social(IDPROXY_PROVIDER, "an-identity")
        social = self._social(SCOUTID_PROVIDER, "a-sub")
        mocked.delay.assert_called_once_with(social_auth_pk=social.pk)

    @patch(f"{SIGNALS}.email_login_method_added")
    def test_nothing_to_send_to(self, mocked):
        self.user.email = ""
        self.user.save()
        self._social(IDPROXY_PROVIDER, "an-identity")
        self._social(SCOUTID_PROVIDER, "a-sub")
        mocked.delay.assert_not_called()

    @scoutid_enabled()
    def test_mail_goes_to_the_address_the_account_already_had(self):
        """
        Not to whatever the incoming credential brought: the point is to reach
        whoever owns the account, which matters most when they are not the
        person who just logged in.
        """
        self.org.providers.create(
            provider_id=SCOUTID_PROVIDER,
            scope="openid profile email",
            client_id="voteit",
            client_secret="s3cret",
        )
        self._social(IDPROXY_PROVIDER, "an-identity")
        social = self._social(SCOUTID_PROVIDER, "a-sub")
        email_login_method_added(social_auth_pk=social.pk)
        self.assertEqual(1, len(mail.outbox))
        sent = mail.outbox[0]
        self.assertEqual(["kim@example.com"], sent.to)
        self.assertIn("ScoutID", sent.body)
        self.assertIn(self.org.title, sent.body)

    def test_a_vanished_credential_is_not_an_error(self):
        social = self._social(IDPROXY_PROVIDER, "an-identity")
        pk = social.pk
        social.delete()
        self.assertIsNone(email_login_method_added(social_auth_pk=pk))
        self.assertEqual(0, len(mail.outbox))

    @scoutid_enabled()
    def test_an_unconfigured_provider_still_names_itself(self):
        """
        No provider row, or a backend left out of this deployment: the bare
        name is a worse label but still says which login it was.
        """
        self._social(IDPROXY_PROVIDER, "an-identity")
        social = self._social(SCOUTID_PROVIDER, "a-sub")
        email_login_method_added(social_auth_pk=social.pk)
        self.assertIn(SCOUTID_PROVIDER, mail.outbox[0].body)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class CleanupSocialAuthLeftoversTests(TestCase):
    """
    A partial is a paused login holding the provider's tokens. Nothing pruned
    them before, because `clearsocial` needs a cron entry somebody remembers.
    """

    def _partial(self, age_days: int):
        partial = Partial.objects.create(
            token=f"token-{age_days}", backend=SCOUTID_PROVIDER, data={}, next_step=3
        )
        Partial.objects.filter(pk=partial.pk).update(
            timestamp=now() - timedelta(days=age_days)
        )
        return partial

    def test_an_abandoned_login_is_dropped(self):
        stale = self._partial(2)
        self.assertEqual(1, cleanup_social_auth_leftovers())
        self.assertFalse(Partial.objects.filter(pk=stale.pk).exists())

    def test_one_still_being_answered_is_left_alone(self):
        fresh = self._partial(0)
        self.assertEqual(0, cleanup_social_auth_leftovers())
        self.assertTrue(Partial.objects.filter(pk=fresh.pk).exists())

    def test_unused_codes_go_too(self):
        code = Code.objects.create(email="kim@example.com", code="abc", verified=False)
        Code.objects.filter(pk=code.pk).update(timestamp=now() - timedelta(days=2))
        cleanup_social_auth_leftovers()
        self.assertFalse(Code.objects.filter(pk=code.pk).exists())

    def test_a_verified_code_is_not_swept_up(self):
        code = Code.objects.create(email="kim@example.com", code="abc", verified=True)
        Code.objects.filter(pk=code.pk).update(timestamp=now() - timedelta(days=2))
        cleanup_social_auth_leftovers()
        self.assertTrue(Code.objects.filter(pk=code.pk).exists())
