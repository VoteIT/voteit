from __future__ import annotations

from logging import getLogger
from typing import Any
from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse
from django.utils.functional import cached_property
from social_core.backends.oauth import BaseOAuth2
from social_core.exceptions import AuthException

from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation

if TYPE_CHECKING:
    from social_django.models import UserSocialAuth

logger = getLogger(__name__)


class OrganisationBackendMixin:
    """
    Resolves the tenant, and that tenant's credentials, for a social auth backend.

    Every ``Organisation`` brings its own OAuth credentials, stored as an
    ``OAuth2Provider`` row keyed by the backend's ``name``. The organisation
    comes from the request's ``Host`` header, as everywhere else.

    Mix in *before* the ``social_core`` backend, so :meth:`get_scope` can extend
    ``DEFAULT_SCOPE`` via ``super()``.
    """

    name: str
    TITLE: str = ""

    @classmethod
    def get_title(cls) -> str:
        return cls.TITLE or cls.name

    @classmethod
    def get_login_url(cls, provider: OAuth2Provider) -> str:
        return reverse("social:begin", args=[cls.name])

    @classmethod
    def get_profile_url(cls, provider: OAuth2Provider) -> str | None:
        """
        Where the user manages their account at the provider.
        """
        return None

    @classmethod
    def get_logout_url(cls, provider: OAuth2Provider) -> str | None:
        """
        Where to send the user to end the provider's own session.
        """
        return None

    @classmethod
    def get_identity_data(cls, social: UserSocialAuth) -> dict[str, list[str]]:
        """
        What the provider vouches for about this person, as ``{scope: [value, ...]}``.

        The shape is the id proxy's, which got here first; every backend
        normalises into it on the way in, so one lookup reads them all. Only
        validated data belongs here -- it decides which invites a user matches
        and which email they may set.

        ``extra_data`` is blanked after a year by
        ``cleanup_extra_data_for_older_users``, so an empty dict is normal.
        """
        return social.extra_data.get("user_data", {})

    @cached_property
    def organisation(self) -> Organisation:
        host = self.strategy.request.get_host().split(":")[0]
        try:
            return Organisation.objects.get(host=host)
        except Organisation.DoesNotExist:
            logger.info("No organisation found for %s ", host)
            raise AuthException(self, "No organisation found for %s " % host)

    @cached_property
    def provider(self) -> OAuth2Provider:
        """
        The credentials this organisation has configured for this backend.
        """
        try:
            return self.organisation.get_provider(self.name)
        except OAuth2Provider.DoesNotExist:
            logger.info(
                "Organisation %s has no %s provider configured",
                self.organisation.host,
                self.name,
            )
            raise AuthException(
                self,
                "No %s login configured for %s" % (self.name, self.organisation.host),
            )

    def get_scope(self) -> list[str]:
        # Sort so we have a deterministic order
        return sorted(
            set(super().get_scope()) | {x for x in self.provider.scope.split() if x}
        )

    def get_key_and_secret(self) -> tuple[str, str]:
        return (self.provider.client_id, self.provider.client_secret)


class IDProxyOAuth2(OrganisationBackendMixin, BaseOAuth2):
    """
    >>> backend = IDProxyOAuth2()
    >>> backend.AUTHORIZATION_URL
    'https://id.voteit.se/o/authorize/'
    >>> backend.ACCESS_TOKEN_URL
    'https://id.voteit.se/o/token/'
    >>> backend.IDENTITY_URL
    'https://id.voteit.se/api/identity/'
    >>> from django.test import override_settings
    >>> with override_settings(SOCIAL_AUTH_IDPROXY_AUTHORIZATION_URL='http://localhost:8001/o/authorize/'):
    ...     backend.authorization_url()
    'http://localhost:8001/o/authorize/'

    >>> with override_settings(SOCIAL_AUTH_IDPROXY_ACCESS_TOKEN_URL='http://localhost:8001/o/token/'):
    ...     backend.access_token_url()
    'http://localhost:8001/o/token/'

    >>> with override_settings(SOCIAL_AUTH_IDPROXY_IDENTITY_URL='http://localhost:8001/api/identity/'):
    ...     backend.identity_url()
    'http://localhost:8001/api/identity/'
    """

    name = "idproxy"
    TITLE = "VoteIT ID"
    REDIRECT_STATE = False
    ID_KEY = "identity_id"
    AUTHORIZATION_URL = "https://id.voteit.se/o/authorize/"
    ACCESS_TOKEN_URL = "https://id.voteit.se/o/token/"
    IDENTITY_URL = "https://id.voteit.se/api/identity/"
    # REVOKE_TOKEN_URL =  "https://id.voteit.se/o/revoke/"
    ACCESS_TOKEN_METHOD = "POST"
    DEFAULT_SCOPE = ["email", "identity"]
    EXTRA_DATA = [
        ("expires_in", "expires"),
        ("user_data",),
        ("is_superuser", "is_superuser", True),
    ]

    @classmethod
    def get_login_url(cls, provider: OAuth2Provider) -> str:
        """
        The id proxy is entered through itself, not through social_django.
        This is to check required data before starting the login process.
        """
        return f"{settings.ID_HOST}/login-to/{provider.organisation.host}"

    @classmethod
    def get_profile_url(cls, provider: OAuth2Provider) -> str:
        return f"{settings.ID_HOST}/"

    @classmethod
    def get_logout_url(cls, provider: OAuth2Provider) -> str:
        return f"{settings.ID_HOST}/log-out"

    def identity_url(self):
        return self.setting("IDENTITY_URL") or self.IDENTITY_URL

    def user_data(self, access_token, *args, **kwargs):
        return self.get_json(
            self.identity_url(),
            headers={
                "Authorization": "Bearer %s" % access_token,
            },
        )

    def get_user_details(self, response):
        fullname, first_name, last_name = self.get_user_names(
            "", response.get("given_name"), response.get("family_name")
        )
        email = ""
        for ud in response.get("user_data", {}):
            if ud.get("scope") == "email":
                email = ud.get("data")
                break
        return {
            "email": email,
            "fullname": fullname,
            "first_name": first_name,
            "last_name": last_name,
            "img_url": response.get("img_url"),  # None is acceptable here
        }

    def extra_data(
        self,
        user,
        uid: str,
        response: dict[str, Any],
        details: dict[str, Any],
        pipeline_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        data = super().extra_data(user, uid, response, details, pipeline_kwargs)
        ud_scopes = {}
        for ud in data.pop("user_data", []):
            type_data = ud_scopes.setdefault(ud["scope"], [])
            type_data.append(ud["data"])
        data["user_data"] = ud_scopes
        return data
