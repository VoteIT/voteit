from urllib.parse import parse_qs

import responses
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from social_core.exceptions import AuthException

from voteit.organisation.backends import IDProxyOAuth2
from voteit.organisation.models import Organisation

User = get_user_model()
_IDENTITY_RESPONSE_JSON = {
    "given_name": "Admin",
    "family_name": "with pass 'admin'",
    "identity_id": "123",
    "user_data": [
        {
            "data": "admin@betahaus.net",
            "has_conflict": False,
            "scope": "email",
            "type": "email",
            "validated": "2021-03-24T16:56:00.043000+01:00",
            "has_recent_validation": False,
        },
        {
            "data": "new@betahaus.net",
            "has_conflict": False,
            "scope": "email",
            "type": "email",
            "validated": "2024-04-12T11:02:57.266794+02:00",
            "has_recent_validation": True,
        },
    ],
    "img_url": "https://image/picture.png",
}


@override_settings(
    LANGUAGE_CODE="en-us",
    SOCIAL_AUTH_IDPROXY_AUTHORIZATION_URL="https://idproxy/o/authorize/",
    SOCIAL_AUTH_IDPROXY_ACCESS_TOKEN_URL="https://idproxy/o/token/",
    SOCIAL_AUTH_IDPROXY_IDENTITY_URL="https://idproxy/api/identity/",
    SOCIAL_AUTH_ALLOWED_REDIRECT_HOSTS=["testing"],
)
class SocialIntegrationTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        # cls.user = User.objects.get(username="moderator")
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        # Unauthenticated will have this hostname
        cls.organisation.host = "testserver"
        cls.organisation.save()
        cls.organisation.provider.client_id = "id-key"
        cls.organisation.provider.client_secret = "id-secret"
        cls.organisation.provider.save()

    def test_begin_login(self):
        # with patch(
        #     "motionen.core.backends.IDProxyOAuth2.AUTHORIZATION_URL",
        #     "https://idproxy/o/auth/",
        # ):
        response = self.client.get("/login/idproxy/")
        location = response.get("Location")
        self.assertTrue(location)
        self.assertIn("client_id=id-key", location)
        self.assertIn("response_type=code", location)
        self.assertIn("scope=email+identity", location)

    def test_check_overrides(self):
        idproxy = IDProxyOAuth2()
        self.assertEqual("https://idproxy/o/authorize/", idproxy.authorization_url())
        self.assertEqual("https://idproxy/o/token/", idproxy.access_token_url())
        self.assertEqual("https://idproxy/api/identity/", idproxy.identity_url())

    @responses.activate
    def test_complete_new_user(self):
        response = self.client.get("/login/idproxy/")
        location = response.get("Location")
        parsed = parse_qs(location)
        state = parsed["state"][0]
        self.assertTrue(state)
        # Mocked response
        token_response = responses.Response(
            method="POST",
            url="https://idproxy/o/token/",
            json={"access_token": "knock knock"},
        )
        responses.add(token_response)
        identity_response = responses.Response(
            method="GET",
            url="https://idproxy/api/identity/",
            json=_IDENTITY_RESPONSE_JSON,
        )
        responses.add(identity_response)
        response = self.client.get("/complete/idproxy/", data={"state": state})
        self.assertEqual(302, response.status_code)
        self.assertEqual(settings.LOGIN_REDIRECT_URL, response.get("Location"))
        # And actual tests
        user = User.objects.all().last()
        self.assertEqual("Admin", user.first_name)
        self.assertEqual("with pass 'admin'", user.last_name)
        self.assertEqual("admin@betahaus.net", user.email)
        self.assertEqual("https://image/picture.png", user.img_url)
        # user social auth
        usa = user.social_auth.first()
        self.assertEqual("123", usa.uid)
        self.assertEqual(
            {"email": ["admin@betahaus.net", "new@betahaus.net"]},
            usa.extra_data.get("user_data"),
        )

    @responses.activate
    def test_complete_existing_user(self):
        user = User.objects.create(username="adminer", email="admin@betahaus.net")
        user.social_auth.create(uid="123", provider="idproxy")
        response = self.client.get("/login/idproxy/")
        location = response.get("Location")
        parsed = parse_qs(location)
        state = parsed["state"][0]
        self.assertTrue(state)
        # Mocked response
        token_response = responses.Response(
            method="POST",
            url="https://idproxy/o/token/",
            json={"access_token": "knock knock"},
        )
        responses.add(token_response)
        identity_response = responses.Response(
            method="GET",
            url="https://idproxy/api/identity/",
            json=_IDENTITY_RESPONSE_JSON,
        )
        responses.add(identity_response)
        response = self.client.get("/complete/idproxy/", data={"state": state})
        self.assertEqual(302, response.status_code)
        self.assertEqual(settings.LOGIN_REDIRECT_URL, response.get("Location"))
        # And actual tests
        user.refresh_from_db()
        self.assertEqual("Admin", user.first_name)
        self.assertEqual("with pass 'admin'", user.last_name)
        self.assertEqual("admin@betahaus.net", user.email)
        self.assertEqual("https://image/picture.png", user.img_url)

    @responses.activate
    def test_complete_existing_user_but_authenticated_as_other(self):
        initial_user = self.organisation.users.create(
            username="initial", email="initial@betahaus.net"
        )
        self.client.force_login(initial_user)
        user = self.organisation.users.create(
            username="adminer", email="admin@betahaus.net"
        )
        user.social_auth.create(uid="123", provider="idproxy")
        response = self.client.get("/login/idproxy/")
        location = response.get("Location")
        parsed = parse_qs(location)
        state = parsed["state"][0]
        self.assertTrue(state)
        # Mocked response
        token_response = responses.Response(
            method="POST",
            url="https://idproxy/o/token/",
            json={"access_token": "knock knock"},
        )
        responses.add(token_response)
        identity_response = responses.Response(
            method="GET",
            url="https://idproxy/api/identity/",
            json=_IDENTITY_RESPONSE_JSON,
        )
        responses.add(identity_response)
        with self.assertRaises(AuthException) as cm:
            self.client.get("/complete/idproxy/", data={"state": state})
        self.assertEqual(
            "You're logged in as another user, logout first.", str(cm.exception)
        )

    @responses.activate
    def test_redirect_to_initial_page(self):
        response = self.client.get("/login/idproxy/?next=http://testing/somepage")
        location = response.get("Location")
        parsed = parse_qs(location)
        state = parsed["state"][0]
        self.assertTrue(state)
        # Mocked response
        token_response = responses.Response(
            method="POST",
            url="https://idproxy/o/token/",
            json={"access_token": "knock knock"},
        )
        responses.add(token_response)
        identity_response = responses.Response(
            method="GET",
            url="https://idproxy/api/identity/",
            json=_IDENTITY_RESPONSE_JSON,
        )
        responses.add(identity_response)
        response = self.client.get("/complete/idproxy/", data={"state": state})
        self.assertEqual(302, response.status_code)
        self.assertEqual("http://testing/somepage", response.get("Location"))

    @responses.activate
    def test_complete_disabled_org(self):
        self.organisation.active = False
        self.organisation.save()
        user = User.objects.create(username="adminer", email="admin@betahaus.net")
        user.social_auth.create(uid="123", provider="idproxy")
        response = self.client.get("/login/idproxy/")
        location = response.get("Location")
        parsed = parse_qs(location)
        state = parsed["state"][0]
        self.assertTrue(state)
        # Mocked response
        token_response = responses.Response(
            method="POST",
            url="https://idproxy/o/token/",
            json={"access_token": "knock knock"},
        )
        responses.add(token_response)
        identity_response = responses.Response(
            method="GET",
            url="https://idproxy/api/identity/",
            json=_IDENTITY_RESPONSE_JSON,
        )
        responses.add(identity_response)
        with self.assertRaises(AuthException) as cm:
            response = self.client.get("/complete/idproxy/", data={"state": state})
        self.assertEqual("This organisation is no longer active.", str(cm.exception))
