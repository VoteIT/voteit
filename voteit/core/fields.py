from django.core.exceptions import ValidationError
from django.db import models

from voteit.core.models import Roles
from voteit.core.role import Role


# FIXME: Refactor this, make it work as a base class to array field!


class RoleField(models.CharField):
    description = "VoteIT single role field"

    def __init__(self, roles_cls, *args, **kwargs):
        kwargs.setdefault("max_length", 20)
        assert issubclass(roles_cls, Roles)
        self.roles_cls = roles_cls
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # del kwargs['max_length']
        kwargs["roles_cls"] = self.roles_cls
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return self.roles_cls.valid_roles.get(value, None)

    def to_python(self, value):
        if value is None or isinstance(value, Role):
            return value

        return self.roles_cls.valid_roles.get(value, None)

    def clean(self, value, model_instance):
        if isinstance(value, Role):
            value = value.name
        if value not in self.roles_cls.valid_roles:
            raise ValidationError(f"Invalid role for {self.roles_cls}")

    def get_prep_value(self, value):
        if isinstance(value, Role):
            value = value.name
        return value
        # return super().get_prep_value(value)
