from __future__ import annotations

from datetime import datetime
from typing import Optional
from typing import TYPE_CHECKING
from django.utils.translation import gettext_lazy as _

from django.conf import settings
from django.db import models
from typing import Type
from voteit.core.abcs import OrganisationContext
from voteit.core.models import BaseContent
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles
from voteit.organisation.utils import get_provider_response_adapters

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.organisation.abcs import ProviderResponseAdapter


class OrganisationRoles(Roles):
    """ Contains assigned meeting roles for a specific meeting and user"""

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organisation_roles",
    )
    context: Organisation = models.ForeignKey(
        "Organisation", on_delete=models.CASCADE, related_name="roles"
    )


class Organisation(BaseContent, RoleContextMixin, OrganisationContext):
    name = "organisation"
    roles_cls = OrganisationRoles
    title: str = models.CharField(max_length=100)

    class Meta:
        verbose_name = _("Organisation")
        verbose_name_plural = _("Organisations")

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


class OAuth2Provider(OrganisationContext):
    """
    This is the identity provider, which uses OAuth2 protocol for exchange.
    We (currently) don't allow more than one.
    Login providers from other services should be added via the id proxy instead.
    """

    name = "oauth2_provider"
    provider_id = models.CharField(max_length=30)
    title = models.CharField(max_length=50)
    organisation: Organisation = models.OneToOneField(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        related_name="provider",
        blank=True,
        null=True,
    )
    scopes: str = models.CharField(
        verbose_name="OAuth scopes, separated by space. Must exist on provider",
        max_length=300,
    )
    client_id: str = models.CharField(max_length=100)
    client_secret: str = models.CharField(max_length=200)
    redirect_url: str = models.URLField()
    auth_url: str = models.URLField()
    token_url: str = models.URLField()
    identity_url: str = models.URLField(
        verbose_name="Should return json with information that can be used to register the user"
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
