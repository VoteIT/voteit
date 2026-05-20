from __future__ import annotations
from typing import TYPE_CHECKING

from rest_framework.exceptions import ValidationError

from voteit.core.rest_api.validators import RoleValidator  # noqa: F401 re-export
from voteit.meeting.dialects import dialect_registry
from voteit.meeting.dialects import get_named_paths


if TYPE_CHECKING:
    from rest_framework.serializers import Serializer


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
