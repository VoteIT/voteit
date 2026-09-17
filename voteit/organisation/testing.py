"""Testing helpers for the SSO layer."""

from __future__ import annotations

from django.conf import settings
from django.test import override_settings
from social_core.backends.oauth import BaseOAuth2

from voteit.organisation.backends import OrganisationBackendMixin
from voteit.organisation.models import OAuth2Provider

DUMMY_PROVIDER = "dummy"


class DummyOAuth2(OrganisationBackendMixin, BaseOAuth2):
    """
    A second social auth backend, so multi-provider behaviour can be tested
    without this app knowing about any of the customer apps in voteit.app.

    Its URLs are fixed strings, so the serializer can be asserted without
    reaching for a real provider's conventions.
    """

    name = DUMMY_PROVIDER
    TITLE = "Dummy login"
    AUTHORIZATION_URL = "https://dummy.example/authorize/"
    ACCESS_TOKEN_URL = "https://dummy.example/token/"

    @classmethod
    def get_profile_url(cls, provider: OAuth2Provider) -> str:
        return f"https://dummy.example/{provider.organisation.host}/account/"

    @classmethod
    def get_logout_url(cls, provider: OAuth2Provider) -> str:
        return "https://dummy.example/logout/"


DUMMY_BACKEND = f"{DummyOAuth2.__module__}.{DummyOAuth2.__qualname__}"


def dummy_backend_enabled() -> override_settings:
    """
    Add :class:`DummyOAuth2` to AUTHENTICATION_BACKENDS for the duration.

    Use as a class decorator or a context manager. Relies on
    voteit.organisation.signals.reload_social_backends to refresh social_core's
    backend cache when the setting changes.
    """
    others = [b for b in settings.AUTHENTICATION_BACKENDS if b != DUMMY_BACKEND]
    return override_settings(AUTHENTICATION_BACKENDS=[*others, DUMMY_BACKEND])
