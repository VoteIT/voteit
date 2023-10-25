from __future__ import annotations
from typing import TYPE_CHECKING

from rest_framework.exceptions import ValidationError

from voteit.meeting.dialects import dialect_registry
from voteit.meeting.dialects import get_named_paths


if TYPE_CHECKING:
    from voteit.core.models import Roles
    from rest_framework.serializers import Serializer


class RoleValidator:
    """
    Ensures that role name is valid for roles class provided on class instantiation.
    """

    roles_cls: type[Roles]

    def __init__(self, roles_cls: type[Roles]):
        self.roles_cls = roles_cls

    def __call__(self, value):
        if value not in self.roles_cls.valid_roles:
            raise ValidationError(f'The role "{value}" is not valid for this context.')


class DialectInstallableValidator:
    requires_context = True

    def __call__(self, value, serializer: Serializer):
        if not value:
            return
        named_paths = {k for k, v in get_named_paths()}
        if value not in named_paths:
            raise ValidationError(f"No meeting dialect named {value}")
        request = serializer.context.get("request")
        org_installable = dialect_registry.get_org_installable(
            organisation=request.user.organisation
        )
        if value not in org_installable:
            raise ValidationError(f"Meeting dialect named {value} isn't installable")
