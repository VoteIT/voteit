from __future__ import annotations
from typing import TYPE_CHECKING

from rest_framework.exceptions import ValidationError

from voteit.meeting.utils import get_named_path_dict
from voteit.meeting.utils import load_dialect_file

if TYPE_CHECKING:
    from voteit.core.models import Roles


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


def validate_dialect_installable(value):
    named_paths = get_named_path_dict()
    if value not in named_paths:
        raise ValidationError(f"No meeting dialect named {value}")
    # May raise exceptions, but we'll want to get those
    dialect = load_dialect_file(value, named_paths[value])
    if not dialect.data.installable:
        raise ValidationError(f"Meeting dialect named {value} isn't installable")
