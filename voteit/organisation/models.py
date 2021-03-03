from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from voteit.core.models import BaseContent, Roles, RoleContextMixin


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
    title: str = models.CharField(max_length=100)
    name = "organisation"
    roles_cls = OrganisationRoles
