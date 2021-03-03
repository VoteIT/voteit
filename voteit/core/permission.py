from __future__ import annotations

from abc import ABC
from abc import ABCMeta
from abc import abstractmethod
from collections import UserString
from typing import Generator
from typing import Optional
from typing import Union

from voteit.core.component import Registry
from voteit.core.schemas import PermissionOutput
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

    def for_model(self, model: str) -> Generator[Permission, None, None]:
        for perm in self.values():
            if model == perm.model:
                yield perm

    def for_context(self, model: str) -> Generator[Permission, None, None]:
        for perm in self.values():
            if model == perm.context:
                yield perm


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
                perm = getattr(cls, k)
                if perm.model is None:
                    perm.model = cls.model
                if perm.context is None:
                    perm.context = perm.model
                reg(perm)

        return cls


class ModelPermissions(ABC, metaclass=MPMeta):
    @property
    @abstractmethod
    def model(self) -> str:
        """ The shortname of the model. For instance "meeting"."""
