from logging import getLogger

from django.core.exceptions import ValidationError
from django.db import models
from typing import Callable
from typing import Iterable

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
    implicit_role: None | Role

    def __init__(
        self,
        *args,
        valid_roles: Iterable[Role] = (),
        max_length=20,
        # implicit_role: None | Role = None,
        **kwargs,
    ):
        # assert implicit_role is None or isinstance(implicit_role, Role)
        self.name_to_role = {}
        for role in valid_roles:
            assert isinstance(role, Role)
            if role.name in self.name_to_role:
                raise ValueError(
                    f"{role} has the same name '{role.name}' as another role which already exists on this field."
                )
            self.name_to_role[role.name] = role
        kwargs.setdefault("default", "")
        # self.implicit_role = implicit_role
        super().__init__(*args, max_length=max_length, **kwargs)

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
        if value is not None:
            return ",".join(sorted(str(x).strip() for x in value if x))

    def to_python(self, value: str | Iterable[str]):
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
                values_set.update({x for x in value.split(",") if x})
        else:
            for item in value:
                if isinstance(item, str):
                    values_set.add(item)
                elif isinstance(item, Role):
                    values_set.add(item.name)
                else:
                    raise ValidationError("Must be string or Role instance")
        # if self.implicit_role:
        #    values_set.add(self.implicit_role.name)
        # for v in values_set:
        #     if v not in self.name_to_role:
        #         raise ValidationError(f"No role letter '{char}'")
        return sorted(values_set)
