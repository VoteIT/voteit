from base64 import b64encode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()


class InviteBasicAuthenticationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.serviceuser = User.objects.create_user(
            username="serviceuser", password="secret"
        )

    @property
    def _cut(self):
        from voteit.access_policy.rest_api.authentication import (
            InviteBasicAuthentication,
        )

        return InviteBasicAuthentication

    def _mk_request(self, pw="secret"):
        credentials = f"serviceuser:{pw}"
        encodedCredentials = str(b64encode(credentials.encode("utf-8")), "utf-8")
        # HTTP_AUTHORIZATION
        return RequestFactory().get(
            "/", HTTP_AUTHORIZATION=f"Basic {encodedCredentials}"
        )

    @override_settings(INVITE_SERVICE_USERS=["serviceuser"])
    def test_authenticate(self):
        request = self._mk_request()
        auth = self._cut()
        result = auth.authenticate(request)
        self.assertEqual((self.serviceuser, None), result)

    @override_settings()
    def test_no_user_in_settings(self):
        del settings.INVITE_SERVICE_USERS
        request = self._mk_request()
        auth = self._cut()
        self.assertRaises(AuthenticationFailed, auth.authenticate, request)

    @override_settings(INVITE_SERVICE_USERS=["serviceuser"])
    def test_wrong_credentials(self):
        del settings.INVITE_SERVICE_USERS
        request = self._mk_request(pw="wrong")
        auth = self._cut()
        self.assertRaises(AuthenticationFailed, auth.authenticate, request)
