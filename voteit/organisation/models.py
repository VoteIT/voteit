from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import Optional
from typing import TYPE_CHECKING
from django.utils.translation import gettext_lazy as _

from django.conf import settings
from django.db import models
from voteit.core.abcs import ABCModel
from voteit.core.models import BaseContent
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class OrganisationContext(ABCModel):
    """ This class may be within the scope of an organisation."""

    @property
    @abstractmethod
    def organisation(self) -> Optional[Organisation]:
        """ Return the organisation object. It could be a ForeignKey relation or a property"""

    class Meta:
        abstract = True


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
    providers: models.QuerySet
    objects: models.Manager
    tos: models.QuerySet
    users: models.QuerySet


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
    consent: datetime = models.DateTimeField(editable=False, auto_now_add=True)
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
