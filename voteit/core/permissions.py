from __future__ import annotations

import warnings
from abc import ABC
from abc import ABCMeta
from collections import UserString
from logging import getLogger


from voteit.core.schemas import PermissionOutput
from voteit.core.utils import get_permission_registry

logger = getLogger(__name__)
# FIXME: context can be None later on, change when that happens


@warnings.deprecated("Use rules instead with contants like voteit.core.PERM")
class Permission(UserString):
    """
    Permissions work as strings, and are equal do the same kind of string

    >>> HELLO_WORLD = Permission("hello_world")
    >>> HELLO_WORLD == "hello_world"
    True

    They can also use pydantic to generate output
    >>> HELLO_WORLD.output().dict(skip_defaults=True, exclude_none=True)
    {'name': 'hello_world', 'context': set()}
    """

    description: str
    model: str = None
    context: set
    # Internal to make testing easier
    perms_cls: type[ModelPermissions] = None
    perms_cls_attr: str = None

    def __init__(
        self,
        name,
        model: str | None = None,
        context: str | set | None = None,
        description: str = "",
    ):
        super().__init__(name)
        if description:
            self.description = description
        if model:
            assert isinstance(model, str), "Specify model short name, like 'meeting'"
            self.model = model
        if context is None:
            context = model
        if isinstance(context, str):
            self.context = {
                context,
            }
        elif context is None:
            # Still none, no model! It might be implicitly assigned later on
            # by ModelPermissions class
            self.context = set()
        elif isinstance(context, set):
            self.context = context
        else:
            raise ValueError("context is not a set or a string")

    @property
    def name(self):
        return self.data

    def output(self) -> PermissionOutput:
        return PermissionOutput.from_orm(self)


class MPMeta(ABCMeta):
    """
    Attach configuration from model attr on ModelPermissions subclasses
    """

    def __new__(mcls, name, bases, namespace, **kwargs):
        cls: ModelPermissions = super().__new__(mcls, name, bases, namespace, **kwargs)
        reg = get_permission_registry()
        if cls.model in reg.model_permissions:
            assert cls == reg.model_permissions[cls.model]
        else:
            reg.model_permissions[cls.model] = cls
        for k, v in namespace.items():
            if isinstance(v, Permission):
                perm: Permission = getattr(cls, k)
                if perm.model is None:
                    assert isinstance(cls.model, str), (
                        f"{cls} doesn't have a valid 'model' attribute set"
                    )
                    perm.model = cls.model
                if not perm.context:
                    # context should not be empty here
                    # since we've fetched a model or crashed
                    perm.context.add(perm.model)
                perm.perms_cls = cls
                perm.perms_cls_attr = k
                reg(perm)
        return cls


class ModelPermissions(ABC, metaclass=MPMeta):
    model = None  # The shortname of the model. For instance "meeting"


NOT_ALLOWED = "__not_allowed"  # Not manually anyway!


class UserPermissions(ModelPermissions):
    model = "user"

    # ADD = Permission("core.add_user") - this is currently not allowed this way
    CHANGE = Permission("core.change_user")
    # DELETE = Permission("core.delete_user")
    VIEW = Permission("core.view_user")
