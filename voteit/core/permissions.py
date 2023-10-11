from __future__ import annotations

from abc import ABC
from abc import ABCMeta
from collections import UserString
from logging import getLogger

from django.conf import settings
from django.utils.functional import cached_property
from rules.permissions import ObjectPermissionBackend

from voteit.core.schemas import PermissionOutput
from voteit.core.utils import get_model_shortname
from voteit.core.utils import get_permission_registry

logger = getLogger(__name__)
# FIXME: context can be None later on, change when that happens


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
                    assert isinstance(
                        cls.model, str
                    ), f"{cls} doesn't have a valid 'model' attribute set"
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


class VerbosePermissionBackend(ObjectPermissionBackend):
    """
    A very verbose ObjectPermissionBackend meant to catch permission checks against the wrong target.
    Set CHECK_PERMISSION_CONTEXT=True to enable.

    It has no other changes compaired to Rules ObjectPermissionBackend, so same docs apply.

    """

    def has_perm(self, user, perm, *args, **kwargs) -> bool:
        if self.check_permission_context:
            assert isinstance(perm, Permission), f"{perm} is not a Permission-instance."
            if args:
                target = args[0]
                if target is None:
                    # Only complain if None isn't a specified context. This will happen though
                    if None not in perm.context:
                        logger.debug(
                            "Permission '%s' was checked with target None", perm
                        )
                else:
                    try:
                        model_shortname = get_model_shortname(target)
                    except ValueError:
                        # Non-model, should never work though
                        model_shortname = target
                    assert model_shortname in perm.context, (
                        f"{perm} was checked against {model_shortname} but only "
                        f"lists these as allowed contexts: {perm.context}"
                    )
            # Simply skip for has_perm with only one arg
        return super().has_perm(user, perm, *args, **kwargs)

    @cached_property
    def check_permission_context(self):
        return getattr(settings, "CHECK_PERMISSION_CONTEXT", False)


class AlwaysTrueSet(set):
    def add(self, item):
        pass

    def __contains__(self, item):
        return True


ANY_SET = AlwaysTrueSet()
NOT_ALLOWED = Permission(
    "__not_allowed", model=ANY_SET, context=ANY_SET
)  # Not manually anyway!


class UserPermissions(ModelPermissions):
    model = "user"

    # ADD = Permission("core.add_user") - this is currently not allowed this way
    CHANGE = Permission("core.change_user")
    # DELETE = Permission("core.delete_user")
    VIEW = Permission("core.view_user")
