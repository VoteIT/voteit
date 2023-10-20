from django.core.exceptions import ValidationError
from django.db import models
from typing import Callable
from typing import Iterable

from voteit.core.role import Role


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
    Charfield that only accepts valid roles and stores them as a sorted string of role-related letters.

    >>> from voteit.core.role import Role
    >>> ROLE_FARMER = Role('farmer', letter='f')
    >>> ROLE_COW = Role('cow', letter='c')
    >>> ROLE_HAMBURGER = Role('hamburger')

    >>> f = RolesField(valid_roles={ROLE_FARMER, ROLE_COW})
    >>> f.valid_role_letters
    'cf'
    >>> RolesField(valid_roles={ROLE_FARMER, "hello"})
    Traceback (most recent call last):
    ...
    AssertionError
    >>> RolesField(valid_roles={ROLE_HAMBURGER})
    Traceback (most recent call last):
    ...
    AssertionError
    """

    def __init__(self, *args, valid_roles=set[Role], max_length=10, **kwargs):
        assert isinstance(valid_roles, set)
        assert len(valid_roles)
        valid_role_letters = []
        self.valid_roles = {}
        for role in valid_roles:
            assert isinstance(role, Role)
            assert role.letter
            if role.letter in valid_role_letters:
                raise ValueError(
                    f"{role} has the same letter '{role.letter}' as another role which already exists on this field."
                )
            valid_role_letters.append(role.letter)
            if role.name in self.valid_roles:
                raise ValueError(
                    f"{role} has the same name '{role.name}' as another role which already exists on this field."
                )
            self.valid_roles[role.name] = role
        self.valid_role_letters = "".join(sorted(valid_role_letters))
        super().__init__(*args, max_length=max_length, **kwargs)

    def to_python(self, value: str | Iterable[str]):
        """
        >>> from voteit.core.role import Role
        >>> ROLE_FARMER = Role('farmer', letter='f')
        >>> ROLE_COW = Role('cow', letter='c')
        >>> ROLE_HAMBURGER = Role('hamburger', letter='h')

        >>> f = RolesField(valid_roles={ROLE_FARMER, ROLE_COW})
        >>> f.to_python({ROLE_FARMER, })
        'f'
        >>> f.to_python([ROLE_FARMER, ROLE_FARMER])
        'f'
        >>> f.to_python([ROLE_FARMER.name, ROLE_COW])
        'cf'
        >>> f.to_python([ROLE_FARMER.name, ROLE_COW, ROLE_HAMBURGER])
        Traceback (most recent call last):
        ...
        django.core.exceptions.ValidationError: ['No role letter h']
        """
        letter_set = set()
        if isinstance(value, str):
            letter_set.update(value)
        else:
            for item in value:
                if isinstance(item, str):
                    if len(item) == 1:
                        letter_set.add(item)
                    else:
                        if item in self.valid_roles:
                            letter_set.add(self.valid_roles[item].letter)
                        else:
                            raise ValidationError(f"No role with name {item}")
                elif isinstance(item, Role):
                    letter_set.add(item.letter)
                else:
                    raise ValidationError(
                        f"{item} must be a a string or a Role-instance"
                    )
        value = "".join(sorted(letter_set))  # Unique and predictable order
        for char in value:
            if char not in self.valid_role_letters:
                raise ValidationError(f"No role letter {char}")
        return value
