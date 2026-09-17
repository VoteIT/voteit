from __future__ import annotations

from logging import getLogger
from typing import Any

from django.conf import settings
from social_core.backends.open_id_connect import OpenIdConnectAuth
from social_core.utils import cache

from voteit.app.scouterna import SCOUTID_PROVIDER
from voteit.organisation.backends import OrganisationBackendMixin
from voteit.organisation.models import OAuth2Provider

logger = getLogger(__name__)

#: Production (``https://id.scouterna.se``) is not live yet.
DEV_OIDC_ENDPOINT = "https://dev.id.scouterna.se/realms/scoutnet"


class ScoutIDOpenIdConnect(OrganisationBackendMixin, OpenIdConnectAuth):
    """
    ScoutID -- the Keycloak-based identity service of Scouterna.

    Members sign in with their Scoutnet credentials. Everything but the issuer
    is discovered from the realm's ``/.well-known/openid-configuration``.

    The ``scoutnet-memberships`` scope carries group and role data. Nothing reads
    it, so it is not requested; add it to the provider's ``scope`` when something
    does.

    >>> backend = ScoutIDOpenIdConnect()
    >>> backend.name
    'scoutid'
    >>> backend.OIDC_ENDPOINT
    'https://dev.id.scouterna.se/realms/scoutnet'
    >>> backend.DEFAULT_SCOPE
    ['openid', 'profile', 'email']
    >>> backend.DEFAULT_USE_PKCE
    True
    >>> backend.PKCE_DEFAULT_CODE_CHALLENGE_METHOD
    'S256'
    """

    name = SCOUTID_PROVIDER
    TITLE = "ScoutID"
    OIDC_ENDPOINT = DEV_OIDC_ENDPOINT
    DEFAULT_SCOPE = ["openid", "profile", "email"]
    # OpenIdConnectAuth turns off the PKCE its own base class enables.
    DEFAULT_USE_PKCE = True
    # Keycloak UUID, stable per user per realm.
    ID_KEY = "sub"
    EXTRA_DATA = [
        ("id_token",),
        ("refresh_token",),
        ("expires_in", "expires"),
        ("sub", "id"),
    ]

    @classmethod
    def get_issuer(cls, provider: OAuth2Provider) -> str:
        """
        The realm to discover configuration from: the organisation's own value,
        then ``SOCIAL_AUTH_SCOUTID_OIDC_ENDPOINT``, then :attr:`OIDC_ENDPOINT`.

        A classmethod because the URLs below are built outside a login request,
        where there is no strategy to read settings through.
        """
        if provider.oidc_endpoint:
            return provider.oidc_endpoint.rstrip("/")
        setting_name = f"SOCIAL_AUTH_{cls.name.upper()}_OIDC_ENDPOINT"
        return getattr(settings, setting_name, None) or cls.OIDC_ENDPOINT

    def oidc_endpoint(self) -> str:
        return self.get_issuer(self.provider)

    @classmethod
    def get_profile_url(cls, provider: OAuth2Provider) -> str:
        """
        Keycloak's account console. Scoutnet remains the source of the data.
        """
        return f"{cls.get_issuer(provider)}/account"

    @classmethod
    def get_logout_url(cls, provider: OAuth2Provider) -> str:
        """
        The realm's ``end_session_endpoint``, built rather than discovered so
        that serialising an organisation never waits on Keycloak.
        """
        return f"{cls.get_issuer(provider)}/protocol/openid-connect/logout"

    # social_core caches these on (class, args). The endpoint is per organisation,
    # so it must be an argument or two realms share one entry.
    @cache(ttl=86400)
    def _oidc_config_for(self, endpoint: str) -> dict[Any, Any]:
        return self.get_json(f"{endpoint}/.well-known/openid-configuration")

    def oidc_config(self) -> dict[Any, Any]:
        return self._oidc_config_for(self.oidc_endpoint())

    @cache(ttl=86400)
    def _jwks_keys_for(self, jwks_uri: str):
        return self.get_remote_jwks_keys()

    def get_jwks_keys(self):
        return self._jwks_keys_for(self.jwks_uri())

    # find_valid_key() calls this on an unknown kid, to pick up a rotated key.
    get_jwks_keys.invalidate = _jwks_keys_for.invalidate  # type: ignore[attr-defined]

    def get_user_details(self, response: dict[str, Any]) -> dict[str, Any]:
        details = super().get_user_details(response)
        # Scoutnet avatar. None is fine, user_details skips empty values.
        details["img_url"] = response.get("picture") or (
            self.id_token.get("picture") if self.id_token else None
        )
        return details
