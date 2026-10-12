from __future__ import annotations

import uuid
from datetime import date
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
from voteit.core.validators import SVGValidator
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER
from voteit.organisation.schemas import validate_colors

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.components.models import OrganisationComponent
    from voteit.meeting.models import Meeting

_marker = object()


def organisation_logo_upload_to(instance, filename):
    return f"org_{instance.pk}/logo/{uuid.uuid4().hex}.svg"


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
    colors: dict = models.JSONField(
        default=dict,
        blank=True,
        validators=[validate_colors],
    )
    logo: str | None = models.FileField(
        upload_to=organisation_logo_upload_to,
        validators=[SVGValidator()],
        blank=True,
        null=True,
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
    primary: bool = models.BooleanField(
        verbose_name="Primary login",
        help_text="Listed before the others.",
        default=False,
    )
    hidden: bool = models.BooleanField(
        verbose_name="Hidden",
        help_text="Not offered as a login option, but still usable.",
        default=False,
    )

    @classmethod
    def visible_for(cls, organisation: Organisation) -> list[OAuth2Provider]:
        """
        The login options to offer, primary first then by title, lowercased.

        Drops the hidden ones, and any whose backend this deployment does not
        have enabled -- a dead login link helps nobody. Sorting is in Python
        because the title comes from the backend class, not the row.
        """
        providers = [
            p for p in organisation.providers.filter(hidden=False) if p.backend
        ]
        return sorted(
            providers, key=lambda p: (not p.primary, p.backend.get_title().lower())
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


@auditlog.register(
    include_fields=[
        "body",
    ],
)
class GlobalTermsOfService(models.Model):
    body: str = RichTextField(
        blank=True,
        default="",
        html_cleaner=relaxed_clean_html,
    )
    version: datetime = models.DateTimeField(
        verbose_name="Version",
        default=now,
        unique=True,
    )
    required_from: date | None = models.DateField(
        verbose_name="Required from",
        null=True,
        blank=True,
        default=None,
    )
    notes: str = RichTextField(
        verbose_name="Why has this changed?",
        html_cleaner=relaxed_clean_html,
        default="",
        blank=True,
    )

    class Meta:
        ordering = ["-version"]
        verbose_name = "Global terms of service"
        verbose_name_plural = "Global terms of service"

    def __str__(self):
        return f"Global ToS {self.version:%Y-%m-%d %H:%M}"


@auditlog.register(
    include_fields=[
        "body",
        "organisation",
        "version",
    ],
)
class TermsOfService(OrganisationContext):
    """
    A terms-of-service document that users must confirm.
    """

    body: str = RichTextField(
        blank=True,
        default="",
        html_cleaner=relaxed_clean_html,
    )
    organisation: Organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        verbose_name="Organisation",
        related_name="tos",
    )
    version: datetime = models.DateTimeField(
        default=now,
    )

    class Meta:
        ordering = ["-version"]
        verbose_name = "Terms Of Service"
        verbose_name_plural = "Terms Of Service"
        constraints = (
            models.UniqueConstraint(
                fields=("organisation", "version"), name="unique org tos version"
            ),
        )

    def __str__(self):
        return f"ToS {self.version:%Y-%m-%d %H:%M} ({self.organisation_id})"

    # Type annotations
    objects: models.Manager


class UserAccept(models.Model):
    user: AbstractUser = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tos_accepts",
    )
    accepted: datetime = models.DateTimeField(editable=False, default=now)

    class Meta:
        ordering = ["-accepted"]
        verbose_name = "User Accepts"
        verbose_name_plural = "User Accepts"

    @property
    def organisation(self) -> Organisation:
        return self.user.organisation

    def __str__(self):
        return f"Accept for {self.user} at {self.accepted:%Y-%m-%d %H:%M}"

    __repr__ = __str__

    # Type annotations
    objects: models.Manager
