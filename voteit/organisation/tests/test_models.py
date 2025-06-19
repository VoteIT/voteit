from datetime import timezone
from datetime import datetime
from datetime import timedelta

import responses
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now

from voteit.organisation.models import AccessToken
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation

User = get_user_model()


class OAuth2ProviderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def test_title_no_org(self):
        provider = OAuth2Provider.objects.create()
        self.assertEqual(f"Provider {provider.pk}", provider.title)


@override_settings(ID_HOST_BACKEND="https://localhost")
class AccessTokenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="user")
        cls.provider = OAuth2Provider.objects.create(
            provider_id="idproxy",
            scope="hello",
            client_id="client_id",
            client_secret="client_secret",
        )

    def test_manager_from_response(self):
        example_response = dict(
            access_token="123",
            expires_in=36000,
            token_type="Bearer",
            refresh_token="123",
            scope=["invites"],
            expires_at=1618295980.7482638,
        )
        access_token = AccessToken.objects.from_response(
            example_response, self.user, self.provider
        )
        self.assertEqual(
            datetime(2021, 4, 13, 6, 39, 40, 748264, tzinfo=timezone.utc),
            access_token.expires_at,
        )

    def test_using_expired_token(self):
        access_token: AccessToken = self.provider.access_tokens.create(
            user=self.user,
            access_token="123",
            expires_in=36000,
            refresh_token="123",
            scope=["invites"],
            expires_at=now() - timedelta(days=1),
        )
        mock_response = dict(
            access_token="123_token",
            expires_in=36000,
            token_type="Bearer",
            refresh_token="123_refresh",
            scope=["invites"],
            expires_at=99999999999,
        )
        mock_profile = {"abc": 1}
        oauth_session = access_token.get_session()
        with responses.RequestsMock() as mocked:
            mocked.add(responses.POST, self.provider.token_url, json=mock_response)
            mocked.add(responses.GET, self.provider.identity_url, json=mock_profile)
            response = oauth_session.get(self.provider.identity_url)
        self.assertEqual(mock_profile, response.json())
        self.assertEqual("123_token", access_token.access_token)
        self.assertEqual("123_refresh", access_token.refresh_token)
