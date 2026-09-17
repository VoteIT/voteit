from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import now
from social_core.backends.utils import load_backends

from voteit.core.abcs import OrganisationContext
from voteit.core.fields import RichTextField
from voteit.core.fields import RolesField
from voteit.core.models import BaseContent
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles
from voteit.core.utils import relaxed_clean_html
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.components.models import OrganisationComponent
    from voteit.meeting.models import Meeting

_marker = object()


@auditlog.register(
    exclude_fields=["id"],
)
class OrganisationRoles(OrganisationContext, Roles):
    """
    Holds the organisation-level roles assigned to a specific user.

    One row per (user, organisation) pair. Valid roles are ``org_manager`` and
    ``meeting_creator``. Changes fire ``roles_added`` / ``roles_removed`` signals.
    """

    name = "organisation_roles"
    valid_roles = {
        ROLE_ORG_MANAGER: ROLE_ORG_MANAGER,
        ROLE_MEETING_CREATOR: ROLE_MEETING_CREATOR,
    }

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organisation_roles",
    )
    assigned: str = RolesField(role_choices=valid_roles.values(), max_length=30)
    context: Organisation = models.ForeignKey(
        "Organisation", on_delete=models.CASCADE, related_name="roles"
    )

    class Meta:
        verbose_name = verbose_name_plural = "Organisation roles"
        unique_together = (("user", "context"),)

    @property
    def organisation(self) -> Organisation | None:
        return self.context

    def get_additional_data(self):
        """
        For auditlog
        """
        return {"o": self.context_id}


@auditlog.register(
    include_fields=[
        "title",
        "body",
        "page_title",
        "body",
        "host",
        "active",
        "help_info",
    ],
)
class Organisation(BaseContent, RoleContextMixin, OrganisationContext):
    """
    Top-level tenant that owns all meetings, users, and settings.

    The ``host`` field maps a hostname to this tenant.
    Every ``User`` in the system belongs to exactly one organisation via
    ``User.organisation``. Superusers and users with ``org_manager`` role can
    access all meetings belonging to the organisation.

    ``active=False`` disables login for all users of this organisation.
    """

    name = "organisation"
    roles_cls = OrganisationRoles
    title: str = models.CharField(
        verbose_name="Title of the organisation itself", max_length=100
    )
    page_title: str = models.CharField(
        verbose_name="Intro page title",
        max_length=150,
        default="",
        blank=True,
    )
    body: str = RichTextField(blank=True, default="", html_cleaner=relaxed_clean_html)
    host: str = models.CharField(
        verbose_name="Host name part, excluding ports. For instance: 'meeting.voteit.se'",
        max_length=60,
        blank=True,
        null=True,
        unique=True,
    )
    active: bool = models.BooleanField(
        verbose_name="Is this organisation active? Disables login if not.",
        default=True,
    )
    help_info: str = RichTextField(
        verbose_name="Where to get help for users",
        blank=True,
        default="",
        html_cleaner=relaxed_clean_html,
    )

    class Meta:
        verbose_name = "Organisation"
        verbose_name_plural = "Organisations"
        ordering = ("title",)

    @property
    def organisation(self) -> Organisation | None:
        # For OrganisationContext
        return self

    def enabled_components(self):
        for component in self.components.filter(enabled=True):
            if component.is_valid:
                yield component

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"Organisation {self.title}"

    def save(self, **kwargs):
        if not self.page_title:
            self.page_title = self.title
        super().save(**kwargs)

    def get_provider(self, provider_id: str) -> OAuth2Provider:
        return self.providers.get(provider_id=provider_id)

    # Type annotations
    objects: models.Manager
    tos: models.QuerySet
    users: models.QuerySet
    meetings: models.QuerySet[Meeting]
    components: models.QuerySet[OrganisationComponent]
    roles: models.QuerySet[OrganisationRoles]
    providers: models.QuerySet[OAuth2Provider]


class OAuth2Provider(OrganisationContext):
    """
    Credentials for one social auth backend, for one organisation.

    ``provider_id`` is the ``name`` of the ``social_core`` backend these
    credentials belong to.
    """

    name = "oauth2_provider"
    organisation: Organisation | None = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        related_name="providers",
    )
    provider_id: str = models.CharField(
        verbose_name="Backend name",
        max_length=30,
        default=IDPROXY_PROVIDER,
    )
    scope: str = models.CharField(
        verbose_name="OAuth scopes",
        help_text="Space separated. Must exist on provider.",
        max_length=300,
    )
    client_id: str = models.CharField(max_length=100)
    client_secret: str = models.CharField(max_length=200)
    oidc_endpoint: str = models.URLField(
        verbose_name="OIDC issuer",
        help_text=(
            "OpenID Connect issuer base URL, without "
            "/.well-known/openid-configuration. Only used by OIDC backends, "
            "and only to override the backend's own default."
        ),
        max_length=300,
        blank=True,
        default="",
    )

    @property
    def backend(self):
        """
        The social auth backend class, or None when it isn't enabled here.
        """
        return load_backends(settings.AUTHENTICATION_BACKENDS).get(self.provider_id)

    @property
    def title(self):
        if self.organisation:
            return f"{self.organisation.title} ({self.provider_id})"
        return f"Provider {self.pk} ({self.provider_id})"

    class Meta:
        verbose_name = "OAuth2Provider"
        verbose_name_plural = "OAuth2Providers"
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "provider_id"],
                name="unique org provider_id",
            ),
        ]

    def clean(self):
        if self.backend is None:
            available = load_backends(settings.AUTHENTICATION_BACKENDS)
            raise ValidationError(
                {
                    "provider_id": (
                        f"'{self.provider_id}' is not an enabled social auth "
                        f"backend. Available: {', '.join(sorted(available))}"
                    )
                }
            )

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"OAuth2Provider {self.title}"

    # Type annotations
    objects: models.Manager


class TermsOfService(BaseContent, OrganisationContext):
    """
    A terms-of-service document that users must accept before using the platform.

    ``required=True`` blocks login until the user has consented. Consents are tracked
    via ``UserConsent``. Multiple TOS documents may exist per organisation; each is
    accepted independently.
    """

    name = "tos"
    title: str = models.CharField(max_length=100, default="")
    required: bool = models.BooleanField(default=False)
    organisation: Organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        verbose_name="Organisation",
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
    """
    Records that a user has accepted a ``TermsOfService`` document.

    ``revoked`` is set when the user withdraws consent. A non-null ``revoked``
    timestamp means the consent is no longer active; check via ``is_revoked``.
    One record per (user, tos) pair (unique constraint).
    """

    name = "user_consent"
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents"
    )
    tos: TermsOfService = models.ForeignKey(
        TermsOfService, on_delete=models.CASCADE, related_name="consents"
    )
    created: datetime = models.DateTimeField(editable=False, default=now)
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
