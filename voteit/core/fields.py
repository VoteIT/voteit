from django.core.exceptions import ValidationError
from django.db import models
from voteit.core.role import roles, Role, RoleMeta


class RoleField(models.CharField):
    description = 'VoteIT Role field'

    def __init__(self, context, *args, **kwargs):
        kwargs['max_length'] = 80
        self.context = context
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs['max_length']
        kwargs['context'] = self.context
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return roles.get(value, None)

    def to_python(self, value):
        if value is None or isinstance(value, Role):
            return value

        return roles.get(value, None)

    def clean(self, value, model_instance):
        valid_roles = roles.get_valid_roles(self.context)
        if value not in valid_roles:
            raise ValidationError(f'Invalid role for context {self.context}')

    def get_prep_value(self, value):
        if isinstance(value, RoleMeta) or isinstance(value, Role):
            return value.name
        return value
