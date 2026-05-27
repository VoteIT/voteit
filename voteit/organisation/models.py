from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.conf import settings
from django.db import models
from django.utils.timezone import now

from voteit.core.abcs import OrganisationContext
from voteit.core.fields import RichTextField
from voteit.core.fields import RolesField
from voteit.core.models import BaseContent
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles
from voteit.core.utils import relaxed_clean_html
from voteit.core.workflows import EnabledWf
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

    The ``host`` field maps a hostname (e.g. ``"meeting.myorg.se"``) to this tenant.
    Every ``User`` in the system belongs to exactly one organisation via
    ``User.organisation``. Superusers and users with ``org_manager`` role can
    access all meetings belonging to the organisation.

    ``active=False`` disables login for all users of this organisation.
    ``OAuth2Provider`` (one-to-one) holds the OAuth2 credentials used for SSO.
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
        for component in self.components.filter(state=EnabledWf.ON):
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

    # Type annotations
    provider: OAuth2Provider  # May raise ObjectDoesNotExist
    objects: models.Manager
    tos: models.QuerySet
    users: models.QuerySet
    meetings: models.QuerySet[Meeting]
    components: models.QuerySet[OrganisationComponent]
    roles: models.QuerySet[OrganisationRoles]


class OAuth2Provider(OrganisationContext):
    """
    This is the identity provider, which uses OAuth2 protocol for exchange.
    We (currently) don't allow more than one.
    Login providers from other services should be added via the id proxy instead.
    """

    name = "oauth2_provider"
    organisation: Organisation | None = models.OneToOneField(
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

    @property
    def id_backend_host(self):
        """
        ID_BACKEND_HOST only needed in dev
        """
        return getattr(settings, "ID_HOST_BACKEND", settings.ID_HOST)

    @property
    def title(self):
        if self.organisation:
            return self.organisation.title
        return f"Provider {self.pk}"

    class Meta:
        verbose_name = "OAuth2Provider"
        verbose_name_plural = "OAuth2Providers"

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
