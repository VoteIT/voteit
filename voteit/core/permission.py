from __future__ import annotations

from abc import ABC
from abc import ABCMeta
from abc import abstractmethod
from collections import UserString
from typing import Generator
from typing import Optional
from typing import Union

from typing import Type
from voteit.core.component import Registry
from voteit.core.schemas import PermissionOutput
from voteit.core.utils import get_model_by_shortname
from voteit.core.utils import get_permission_registry


class PermissionRegistry(Registry):
    """
    Permission registries are dicts with instances of the Permission-class as values.
    They can be created and self-registered via create().

    Their primary function is documentation - making the permission system as understandable and transparent
    to the frontend developer as possible.

    >>> registry = PermissionRegistry(Permission)
    >>> MAKE_SODA = Permission("make_soda", "streamer")
    >>> registry(MAKE_SODA)
    'make_soda'

    >>> "make_soda" in registry
    True
    """

    ATTRS_TO_CHECK = ("add", "change", "view", "delete")

    def for_model(self, model: str) -> Generator[Permission, None, None]:
        for perm in self.values():
            if model == perm.model:
                yield perm

    def for_context(self, model: str) -> Generator[Permission, None, None]:
        for perm in self.values():
            if model == perm.context:
                yield perm

    def validate_registry(self):
        """Make sure registered permissions make sense.
        This must be run after model ready.

        Example:
        >>> registry = PermissionRegistry(Permission)

        Bad model picked up
        >>> perm = Permission("hello_world", model="boho")
        >>> registry(perm)
        'hello_world'
        >>> registry.validate_registry()
        Traceback (most recent call last):
        ...
        ValueError

        Contexts are checked too
        >>> registry.clear()
        >>> perm = Permission("hello_world", model="meeting", context="404")
        >>> registry(perm)
        'hello_world'
        >>> registry.validate_registry()
        Traceback (most recent call last):
        ...
        ValueError

        Any permission names that doesn't match Djangos model permissions
        for add, change, view, delete will cause errors too.
        >>> registry.clear()
        >>> perm = Permission("meeting.add_some_meeting", model="meeting")
        >>> perm.perms_cls_attr = "ADD"
        >>> registry(perm)
        'meeting.add_some_meeting'
        >>> registry.validate_registry()
        Traceback (most recent call last):
        ...
        ValueError

        """
        for permission in self.values():
            try:
                model = get_model_by_shortname(permission.model)
            except Exception:
                breakpoint()
            if model is None:
                raise ValueError(
                    f"Permission {permission} references a model that doesn't exist: '{permission.model}'"
                )
            context_model = get_model_by_shortname(permission.context)
            if context_model is None:
                raise ValueError(
                    f"Permission {permission} has a context that references a model that doesn't exist: '{permission.context}'"
                )
            if permission.perms_cls_attr.lower() in self.ATTRS_TO_CHECK:
                dj_perm = (
                    f"{model._meta.app_label}.{permission.perms_cls_attr.lower()}_"
                    f"{model._meta.model_name.lower()}"
                )
                if dj_perm != permission:
                    raise ValueError(
                        f"Djangos object permissions {permission.perms_cls_attr} "
                        f"for model {permission.model} to have the format {dj_perm}. "
                        f"Got: {permission}"
                    )


class Permission(UserString):
    """
    Permissions work as strings, and are equal do the same kind of string

    >>> HELLO_WORLD = Permission("hello_world")
    >>> HELLO_WORLD == "hello_world"
    True

    They can also use pydantic to generate output
    >>> HELLO_WORLD.output().dict(skip_defaults=True, exclude_none=True)
    {'name': 'hello_world'}
    """

    description: str
    model: str = None
    context: str = None
    # Internal to make testing easier
    perms_cls: Type[ModelPermissions] = None
    perms_cls_attr: str = None

    def __init__(
        self, name, model: str = None, context: str = None, description: str = ""
    ):
        super().__init__(name)
        if description:
            self.description = description
        if model:
            assert isinstance(model, str), "Specify model short name, like 'meeting'"
            self.model = model
        if context is None:
            context = model
        self.context = context

    @property
    def name(self):
        return self.data

    def output(self) -> PermissionOutput:
        return PermissionOutput.from_orm(self)


class MPMeta(ABCMeta):
    def __new__(mcls, name, bases, namespace, **kwargs):
        cls: ModelPermissions = super().__new__(mcls, name, bases, namespace, **kwargs)
        reg = get_permission_registry()
        for (k, v) in namespace.items():
            if isinstance(v, Permission):
                perm: Permission = getattr(cls, k)
                if perm.model is None:
                    assert isinstance(
                        cls.model, str
                    ), f"{cls} doesn't have a valid 'model' attribute set"
                    perm.model = cls.model
                if perm.context is None:
                    perm.context = perm.model
                perm.perms_cls = cls
                perm.perms_cls_attr = k
                reg(perm)
        return cls


class ModelPermissions(ABC, metaclass=MPMeta):
    model = None  # The shortname of the model. For instance "meeting"
