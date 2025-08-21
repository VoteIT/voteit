from __future__ import annotations
from logging import getLogger

from auditlog.registry import auditlog
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from typing import TYPE_CHECKING

from voteit.access_policy.models import AccessPolicy
from voteit.access_policy.registries import access_policies
from voteit.core.fields import RolesField
from voteit.meeting.models import MeetingRoles

if TYPE_CHECKING:
    from voteit.core.role import Role

__all__ = ["AutomaticAccess"]


logger = getLogger(__name__)


@access_policies
@auditlog.register(
    exclude_fields=[
        "id",
    ],
)
class AutomaticAccess(AccessPolicy):
    """
    Give access to any user that requests access.
    """

    name: str = "automatic"
    title: str = _("Give users access automatically")
    roles_given: list[Role] = RolesField(
        max_length=60, role_choices=MeetingRoles.valid_roles.values()
    )
    exporters = {"meeting": {}}
    importers = {"meeting": {}, "organisation": {}}

    def assign(self, user: AbstractUser):
        if self.roles_given:
            self.meeting.add_roles(user, *self.roles_given)

    objects: models.Manager
