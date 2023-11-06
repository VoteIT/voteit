from logging import getLogger

from django.core.exceptions import ValidationError
from django.db import models
from typing import Callable
from typing import Iterable

from django import forms

from voteit.core.role import Role

logger = getLogger(__name__)


class RichTextField(models.TextField):
    html_cleaner: Callable[[str], str]

    def __init__(self, html_cleaner: Callable[[str], str] = None, *args, **kwargs):
        if html_cleaner is None:
            from voteit.core.utils import strict_clean_html

            html_cleaner = strict_clean_html
        self.html_cleaner = html_cleaner
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add) -> str:
        value = super().pre_save(model_instance, add)
        cleaned_value = self.html_cleaner(value)
        if cleaned_value != value:
            setattr(model_instance, self.attname, cleaned_value)
        return cleaned_value


class RolesField(models.CharField):
    """
    Charfield that only accepts valid roles and stores them as a sorted string.

    >>> from voteit.core.role import Role
    >>> ROLE_FARMER = Role('farmer')
    >>> ROLE_COW = Role('cow')
    >>> ROLE_HAMBURGER = Role('hamburger')

    >>> f = RolesField(valid_roles={ROLE_FARMER, ROLE_COW})
    >>> sorted(f.name_to_role)
    ['cow', 'farmer']
    >>> RolesField(valid_roles={ROLE_FARMER, "hello"})
    Traceback (most recent call last):
    ...
    AssertionError
    """

    name_to_role: dict[str, Role]
    description = "Roles storage, saved as csv but handled as list"

    def __init__(
        self,
        *args,
        valid_roles: Iterable[Role] = (),
        max_length=20,
        **kwargs,
    ):
        self.name_to_role = {}
        for role in valid_roles:
            assert isinstance(role, Role)
            if role.name in self.name_to_role:
                raise ValueError(
                    f"{role} has the same name '{role.name}' as another role which already exists on this field."
                )
            self.name_to_role[role.name] = role
        kwargs.setdefault("default", "")
        kwargs.setdefault(
            "choices", ((r.name, r.title) for r in self.name_to_role.values())
        )
        super().__init__(
            *args,
            max_length=max_length,
            **kwargs,
        )

    def get_internal_type(self):
        return "CharField"

    def from_db_value(self, value: str, expression, connection) -> list[str]:
        """
        >>> f = RolesField()
        >>> f.from_db_value("a,b,c", None, None)
        ['a', 'b', 'c']
        >>> f.from_db_value("", None, None)
        []
        >>> f.from_db_value(None, None, None)
        []
        """
        if isinstance(value, str):
            if value:
                return value.split(",")
        return []

    def get_prep_value(self, value: Iterable[Role | str]) -> str:
        value = self.to_python(value)
        if value:
            return ",".join(value)
        # How do we handle empty string here?

    def to_python(self, value: str | Iterable[str]) -> list[str]:
        """
        >>> from voteit.core.role import Role
        >>> ROLE_FARMER = Role('f', title="Farmer")
        >>> ROLE_COW = Role('c', title="Cow")
        >>> ROLE_HAMBURGER = Role('h', title='Hamburger')

        >>> f = RolesField(valid_roles={ROLE_FARMER, ROLE_COW})
        >>> f.to_python({ROLE_FARMER, })
        ['f']
        >>> f.to_python([ROLE_FARMER, ROLE_FARMER])
        ['f']
        >>> f.to_python([ROLE_FARMER.name, ROLE_COW])
        ['c', 'f']
        """
        values_set = set()
        if isinstance(value, str):
            if value:
                values_set.update({x.strip() for x in value.split(",") if x})
        else:
            for item in value:
                if isinstance(item, str):
                    values_set.add(item.strip())
                elif isinstance(item, Role):
                    values_set.add(item.name)
                else:
                    raise ValidationError("Must be string or Role instance")
        for name in values_set:
            if name not in self.name_to_role:
                raise ValidationError(f"{name} is not a valid role for this context")
        return sorted(values_set)

    def formfield(self, **kwargs):
        defaults = {
            "choices": self.choices,
            "widget": forms.CheckboxSelectMultiple,
        }
        defaults.update(kwargs)
        return forms.MultipleChoiceField(**defaults)

    def validate(self, value, model_instance):
        if not self.editable:
            return

        if value is None and not self.null:
            raise ValidationError(self.error_messages["null"], code="null")

        if not self.blank and value in self.empty_values:
            raise ValidationError(self.error_messages["blank"], code="blank")

        if self.choices is not None and value not in self.empty_values:
            # value should be an array here
            valid_choices = set()
            for option_key, option_value in self.choices:
                if isinstance(option_value, (list, tuple)):
                    # This is an optgroup, so look inside the group for
                    # options.
                    for optgroup_key, _ in option_value:
                        valid_choices.add(optgroup_key)
                elif option_key:
                    valid_choices.add(option_key)
            for v in value:
                if v not in valid_choices:
                    raise ValidationError(
                        self.error_messages["invalid_choice"],
                        code="invalid_choice",
                        params={"value": v},
                    )
