"""Testing helpers for the SSO layer."""

from __future__ import annotations

from django.conf import settings
from django.test import override_settings
from social_core.backends.oauth import BaseOAuth2

from voteit.organisation.backends import OrganisationBackendMixin
from voteit.organisation.models import OAuth2Provider

DUMMY_PROVIDER = "dummy"
ALT_DUMMY_PROVIDER = "dummy-alt"


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


class AltDummyOAuth2(DummyOAuth2):
    """
    A third backend. Its title starts lowercase on purpose, so provider
    ordering cannot pass by comparing raw strings.
    """

    name = ALT_DUMMY_PROVIDER
    TITLE = "alpha login"


def _path(cls) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


DUMMY_BACKEND = _path(DummyOAuth2)
ALT_DUMMY_BACKEND = _path(AltDummyOAuth2)


def dummy_backend_enabled() -> override_settings:
    """
    Add the dummy backends to AUTHENTICATION_BACKENDS for the duration.

    Use as a class decorator or a context manager. Relies on
    voteit.organisation.signals.reload_social_backends to refresh social_core's
    backend cache when the setting changes.
    """
    added = [DUMMY_BACKEND, ALT_DUMMY_BACKEND]
    others = [b for b in settings.AUTHENTICATION_BACKENDS if b not in added]
    return override_settings(AUTHENTICATION_BACKENDS=[*others, *added])
