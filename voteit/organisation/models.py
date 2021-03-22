from __future__ import annotations

from typing import TYPE_CHECKING

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
    title: str = models.CharField(max_length=100)
    roles_cls = OrganisationRoles


# PUA
# Kontaktperson
# Kontaktadress etc...
# Scopes?
# Logga
# Supportadress?
