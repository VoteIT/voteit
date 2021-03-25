from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from django.utils.translation import gettext_lazy as _

from django.conf import settings
from django.db import models
from voteit.core.models import BaseContent
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


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


class Organisation(BaseContent, RoleContextMixin):
    name = "organisation"
    roles_cls = OrganisationRoles
    title: str = models.CharField(max_length=100)

    class Meta:
        verbose_name = _("Organisation")
        verbose_name_plural = _("Organisations")

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"Organisation {self.title}"

    # Type annotations
    providers: models.QuerySet
    objects: models.Manager
    tos: models.QuerySet


class TermsOfService(BaseContent):
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


class UserConsent(models.Model):
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents"
    )
    tos: TermsOfService = models.ForeignKey(
        TermsOfService, on_delete=models.CASCADE, related_name="consents"
    )
    consent: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    revoked: datetime = models.DateTimeField(null=True, blank=True)

    @property
    def is_revoked(self):
        return self.revoked is not None

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
