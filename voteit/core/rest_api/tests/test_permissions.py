from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()


class IDProxyApiKeyTests(TestCase):
    @property
    def _cut(self):
        from voteit.core.rest_api.permissions import (
            HasIDProxyAPIKey,
        )

        return HasIDProxyAPIKey

    def _mk_request(self, key="secret"):
        return RequestFactory().get("/", HTTP_API_KEY=key)

    @override_settings(ID_PROXY_API_KEY="secret")
    def test_permission(self):
        request = self._mk_request()
        permission = self._cut()
        self.assertTrue(permission.has_permission(request, None))

    def test_not_set(self):
        try:
            del settings.ID_PROXY_API_KEY
        except AttributeError:
            pass
        request = self._mk_request()
        permission = self._cut()
        self.assertRaises(
            AuthenticationFailed, permission.has_permission, request, None
        )

    @override_settings(ID_PROXY_API_KEY="")
    def test_empty_keys(self):
        request = self._mk_request(key="")
        permission = self._cut()
        self.assertRaises(
            AuthenticationFailed, permission.has_permission, request, None
        )
