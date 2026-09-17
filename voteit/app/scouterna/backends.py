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

#: Identity scope for the Scoutnet membership number. Named like an id proxy
#: scope because it lands in the same ``user_data`` dict.
SCOUTNET_MEMBER_NO = "scoutnet_member_no"


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

    def _claim(self, response: dict[str, Any], key: str) -> Any:
        """
        A claim may come from userinfo or only from the id token, depending on
        how the realm's client is configured. Mirrors ``OpenIdConnectAuth``'s
        own lookup in ``get_user_details``.
        """
        if key in response:
            return response[key]
        return self.id_token.get(key) if self.id_token else None

    def get_user_details(self, response: dict[str, Any]) -> dict[str, Any]:
        details = super().get_user_details(response)
        # Scoutnet avatar. None is fine, user_details skips empty values.
        details["img_url"] = self._claim(response, "picture")
        return details

    def get_member_no(self, response: dict[str, Any]) -> str | None:
        """
        The Scoutnet membership number, from ``preferred_username``, which is
        always ``scoutnet|<member_no>``.
        """
        username = self._claim(response, "preferred_username") or ""
        _prefix, sep, member_no = username.partition("|")
        if not sep or not member_no:
            logger.warning("Unexpected preferred_username format: %r", username)
            return None
        return member_no

    def extra_data(
        self,
        user,
        uid: str,
        response: dict[str, Any],
        details: dict[str, Any],
        pipeline_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Store what ScoutID vouches for as ``user_data``, the shape
        ``OrganisationBackendMixin.get_identity_data`` reads for every backend.

        The email goes in only when ScoutID says it is verified: it decides
        invite matching and which address the user may set on their profile.
        """
        data = super().extra_data(user, uid, response, details, pipeline_kwargs)
        identity: dict[str, list[str]] = {}
        email = self._claim(response, "email")
        if email and self._claim(response, "email_verified"):
            identity["email"] = [email]
        if member_no := self.get_member_no(response):
            identity[SCOUTNET_MEMBER_NO] = [member_no]
        data["user_data"] = identity
        return data
