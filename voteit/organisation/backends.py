from logging import getLogger
from typing import Any

from django.utils.functional import cached_property
from social_core.backends.oauth import BaseOAuth2
from social_core.exceptions import AuthException

from voteit.organisation.models import Organisation

logger = getLogger(__name__)


class IDProxyOAuth2(BaseOAuth2):
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
    REDIRECT_STATE = True
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
    ]
    DEFAULT_SCOPE = ["identity"]

    def get_scope(self) -> list[str]:
        # Sort so we have a deterministic order
        return sorted(
            set(super().get_scope())
            | {x for x in self.organisation.provider.scope.split() if x}
        )

    def authorization_url(self):
        return self.setting("AUTHORIZATION_URL") or self.AUTHORIZATION_URL

    def access_token_url(self):
        return self.setting("ACCESS_TOKEN_URL") or self.ACCESS_TOKEN_URL

    def identity_url(self):
        return self.setting("IDENTITY_URL") or self.IDENTITY_URL

    # def revoke_token_url(self, **kwargs):
    #     return self.setting("REVOKE_TOKEN_URL")

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

    def get_key_and_secret(self) -> tuple[str, str]:
        return (
            self.organisation.provider.client_id,
            self.organisation.provider.client_secret,
        )

    @cached_property
    def organisation(self):
        host = self.strategy.request.get_host().split(":")[0]
        try:
            return Organisation.objects.select_related("provider").get(host=host)
        except Organisation.DoesNotExist:
            logger.info("No organisation found for %s ", host)
            raise AuthException(self, "No organisation found for %s " % host)
