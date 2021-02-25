from __future__ import annotations

from collections import UserString
from typing import Generator
from typing import Optional
from typing import Union

from voteit.core.component import Registry
from voteit.core.schemas import PermissionOutput


class PermissionRegistry(Registry):
    """
    Permission registries are dicts with instances of the Permission-class as values.
    They can be created and self-registered via create().

    Their primary function is documentation - making the permission system as understandable and transparent
    to the frontend developer as possible.

    >>> registry = PermissionRegistry(Permission)
    >>> MAKE_SODA = registry.create("make_soda", "Streamer")
    >>> MAKE_SODA
    'make_soda'

    >>> "make_soda" in registry
    True
    """

    def create(
        self, permission: Union[Permission, str], model_name=None, **kwargs
    ) -> Permission:
        """ Create and register permission. Returns new permission object. """
        if not isinstance(permission, Permission):
            permission = Permission(permission, model_name, **kwargs)
        return self(permission)

    def for_model(self, model_name: str) -> Generator[Permission, None, None]:
        for perm in self.values():
            if model_name == perm.model_name:
                yield perm


class Permission(UserString):
    """
    Permissions work as strings, and are equal do the same kind of string

    >>> HELLO_WORLD = Permission("hello_world")
    >>> HELLO_WORLD == "hello_world"
    True

    They can also use pydantic to generate output
    >>> HELLO_WORLD.output().dict(skip_defaults=True)
    {'name': 'hello_world'}
    """

    description: str
    model_name: Optional[str]

    def __init__(self, name, model_name: Optional[str] = None, description: str = ""):
        super().__init__(name)
        if description:
            self.description = description
        if model_name:
            assert isinstance(model_name, str), "Specify model name, like 'Meeting'"
            self.model_name = model_name

    @property
    def name(self):
        return self.data

    def output(self) -> PermissionOutput:
        return PermissionOutput.from_orm(self)
