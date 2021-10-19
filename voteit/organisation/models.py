from __future__ import annotations

from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from pytz import utc
from requests_oauthlib import OAuth2Session

from voteit.core.abcs import OrganisationContext
from voteit.core.fields import RichTextField
from voteit.core.models import BaseContent
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles
from voteit.core.utils import relaxed_clean_html
from voteit.organisation.schemas import OAuthTokenSchema
from voteit.organisation.utils import get_provider_response_adapters

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.organisation.abcs import ProviderResponseAdapter

_marker = object()


class OrganisationRoles(Roles):
    """Contains assigned meeting roles for a specific meeting and user"""

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organisation_roles",
    )
    context: Organisation = models.ForeignKey(
        "Organisation", on_delete=models.CASCADE, related_name="roles"
    )

    class Meta:
        verbose_name = verbose_name_plural = _("Organisation roles")


class Organisation(BaseContent, RoleContextMixin, OrganisationContext):
    name = "organisation"
    roles_cls = OrganisationRoles
    title: str = models.CharField(max_length=100)
    body: str = RichTextField(blank=True, default="", html_cleaner=relaxed_clean_html)

    class Meta:
        verbose_name = _("Organisation")
        verbose_name_plural = _("Organisations")
        ordering = ("title",)

    @property
    def organisation(self) -> Optional[Organisation]:
        # For OrganisationContext
        return self

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"Organisation {self.title}"

    # Type annotations
    provider: Optional[OAuth2Provider]
    objects: models.Manager
    tos: models.QuerySet
    users: models.QuerySet
    meetings: models.QuerySet


class OAuth2Provider(OrganisationContext):
    """
    This is the identity provider, which uses OAuth2 protocol for exchange.
    We (currently) don't allow more than one.
    Login providers from other services should be added via the id proxy instead.
    """

    name = "oauth2_provider"
    provider_id: str = models.CharField(max_length=30)
    title: str = models.CharField(max_length=50)
    organisation: Optional[Organisation] = models.OneToOneField(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        related_name="provider",
        blank=True,
        null=True,
    )
    scope: str = models.CharField(
        verbose_name="OAuth scopes",
        help_text="Space separated. Must exist on provider.",
        max_length=300,
    )
    client_id: str = models.CharField(max_length=100)
    client_secret: str = models.CharField(max_length=200)
    redirect_url: str = models.URLField()
    auth_url: str = models.URLField()
    token_url: str = models.URLField()
    identity_url: str = models.URLField(
        verbose_name="Identity URL",
        help_text="URL that returns Json data that can be used to register the user.",
    )

    class Meta:
        verbose_name = "OAuth2Provider"
        verbose_name_plural = "OAuth2Providers"

    @property
    def response_adapter(self) -> Type[ProviderResponseAdapter]:
        return get_provider_response_adapters()[self.provider_id]

    def save(self, **kw):
        adapters = get_provider_response_adapters()
        if self.provider_id not in adapters:
            raise ValueError(
                "%s is not registered in provider_response_adapters", self.provider_id
            )
        super().save(**kw)

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"OAuth2Provider {self.title}"

    # Type annotations
    objects: models.Manager
    access_tokens: models.QuerySet


class AccessTokenManager(models.Manager):
    def from_response(
        self,
        response: Dict,
        user: AbstractUser,
        provider: OAuth2Provider,
    ) -> AccessToken:
        """
        Create or update an access token from response
        """
        token = OAuthTokenSchema(**response)
        access_token: Optional[AccessToken] = AccessToken.objects.filter(
            user=user,
            provider=provider,
        ).first()
        # We could use get or create but we would still need to touch all attributes
        if access_token is None:
            return self.create_from_pydantic(token, user=user, provider=provider)
        else:
            access_token.save_from_pydantic(token)
            return access_token

    def create_from_pydantic(
        self,
        token: OAuthTokenSchema,
        user: AbstractUser = None,
        provider: OAuth2Provider = None,
    ) -> AccessToken:
        # FIXME: This should use the already filtered user as default
        return AccessToken.objects.create(
            scope=token.scope,
            expires_at=datetime.fromtimestamp(token.expires_at, tz=utc),
            expires_in=token.expires_in,
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            user=user,
            provider=provider,
        )


class AccessToken(models.Model):
    """
    OAuth AccessToken

    Note that we're not authenticating these ourselves but they're for other resources.
    """

    name: str = "access_token"
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_tokens",
    )
    provider: OAuth2Provider = models.ForeignKey(
        OAuth2Provider,
        on_delete=models.CASCADE,
        related_name="access_tokens",
    )
    created: datetime = models.DateTimeField(auto_now_add=True)
    updated: datetime = models.DateTimeField(auto_now=True)
    scope: List[str] = ArrayField(models.CharField(max_length=50), default=list)
    expires_at: datetime = models.DateTimeField()
    expires_in: int = models.PositiveIntegerField()
    access_token: str = models.CharField(max_length=100)
    refresh_token: str = models.CharField(max_length=100)

    @property
    def is_expired(self) -> bool:
        """
        Essentially if it should refresh
        """
        return now() > self.expires_at

    def save_from_pydantic(self, token: OAuthTokenSchema):
        self.scope = token.scope
        self.expires_at = datetime.fromtimestamp(token.expires_at, tz=utc)
        self.expires_in = token.expires_in
        self.access_token = token.access_token
        self.refresh_token = token.refresh_token
        self.save()

    def as_dict(self) -> Dict:
        """
        This dict is what OAuthLib expects as "token" kwarg
        """
        return OAuthTokenSchema(
            scope=self.scope,
            expires_at=self.expires_at,
            expires_in=self.expires_in,
            access_token=self.access_token,
            refresh_token=self.refresh_token,
        ).dict()

    def token_handler(self, response: Dict):
        token = OAuthTokenSchema(**response)
        self.save_from_pydantic(token)

    def get_session(self) -> OAuth2Session:
        refresh_kwargs = {
            "client_id": self.provider.client_id,
            "client_secret": self.provider.client_secret,
        }
        return OAuth2Session(
            self.provider.client_id,
            token=self.as_dict(),
            auto_refresh_url=self.provider.token_url,
            auto_refresh_kwargs=refresh_kwargs,
            token_updater=self.token_handler,
        )

    def __str__(self):
        return f"Access token for {self.user.userid}"

    objects = AccessTokenManager()


class TermsOfService(BaseContent, OrganisationContext):
    name = "tos"
    title: str = models.CharField(max_length=100, default="")
    required: bool = models.BooleanField(default=False)
    organisation: Organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        verbose_name=_("Organisation"),
        related_name="tos",
    )

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"TOS: {self.title}"

    # Type annotations
    objects: models.Manager
    consents: models.QuerySet


class UserConsent(OrganisationContext):
    name = "user_consent"
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents"
    )
    tos: TermsOfService = models.ForeignKey(
        TermsOfService, on_delete=models.CASCADE, related_name="consents"
    )
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    revoked: datetime = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=("user", "tos"), name="unique user tos"),
        )

    @property
    def is_revoked(self):
        return self.revoked is not None

    @property
    def organisation(self) -> Organisation:
        return self.tos.organisation

    def __str__(self):
        return f"Consent to {self.tos} for {self.user.username}"

    __repr__ = __str__

    # Type annotations
    objects: models.Manager


# PUA <- organisationen själv
# Kontaktperson
# Kontaktadress etc...
# Scopes?
# Logga
# Supportadress?
