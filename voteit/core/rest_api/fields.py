from rest_framework import fields
from rest_framework.exceptions import ValidationError

from voteit.core.role import Role
from voteit.core.fields import RolesField as ModelRolesField


class RoleField(fields.CharField):
    def __init__(self, valid_roles: set[Role] | None = None, **kwargs):
        self.valid_roles = valid_roles
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, Role):
            data = str(data)
        return super().to_internal_value(data)

    def run_validation(self, data=fields.empty):
        value = super().run_validation(data)
        if value not in self._get_valid_roles():
            raise ValidationError(f"{value} is not a valid role", code="invalid")
        return value

    def _get_valid_roles(self) -> set[str]:
        if self.valid_roles:
            return self.valid_roles
        # Different usecases for field, for instance single role?
        assert (
            self.parent is not None
        ), "RoleField must be bound to a parent if roles aren't specified as 'valid_roles'"
        try:
            model = self.root.Meta.model
        except AttributeError as exc:
            raise AttributeError(
                "RoleField must be used on a ModelSerializer with model set"
            ) from exc
        f = model._meta.get_field(self.parent.source)
        assert isinstance(f, ModelRolesField)
        return set(f.name_to_role)


class RolesField(fields.ListField):
    child = RoleField()

    def __init__(self, valid_roles: set[Role] | None = None, **kwargs):
        self.valid_roles = valid_roles
        super().__init__(**kwargs)
        self.child.valid_roles = self.valid_roles
