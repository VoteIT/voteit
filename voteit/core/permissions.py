from __future__ import annotations

from abc import ABC
from abc import ABCMeta
from collections import UserString
from logging import getLogger
from typing import Generator
from typing import Optional
from typing import Set
from typing import Type
from typing import Union

from django.conf import settings
from django.utils.functional import cached_property
from rules.permissions import ObjectPermissionBackend
from voteit.core.component import Registry
from voteit.core.schemas import PermissionOutput
from voteit.core.utils import get_model_by_shortname
from voteit.core.utils import get_model_shortname
from voteit.core.utils import get_permission_registry


logger = getLogger(__name__)
# FIXME: context can be None later on, change when that happens


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
        """
        Fetch permissions checked with a specific context as target.
        >>> registry = PermissionRegistry(Permission)

        >>> perm = Permission("hello_world", context="yay")
        >>> registry(perm)
        'hello_world'
        >>> perm = Permission("bye_world", context={"boho", "adios", "yay"})
        >>> registry(perm)
        'bye_world'

        >>> set(registry.for_context("boho"))
        {'bye_world'}
        >>> set(registry.for_context("yay")) == {'bye_world', 'hello_world'}
        True

        """
        for perm in self.values():
            if model in perm.context:
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
            model = get_model_by_shortname(permission.model)
            if model is None:
                raise ValueError(
                    f"Permission {permission} references a model that doesn't exist: '{permission.model}'"
                )
            if permission.context:
                for context_name in permission.context:
                    context_model = get_model_by_shortname(context_name)
                    if context_model is None:
                        raise ValueError(
                            f"Permission {permission} has a context that references a model that doesn't exist: '{context_name}'"
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
    {'name': 'hello_world', 'context': set()}
    """

    description: str
    model: str = None
    context: Set
    # Internal to make testing easier
    perms_cls: Type[ModelPermissions] = None
    perms_cls_attr: str = None

    def __init__(
        self,
        name,
        model: Optional[str] = None,
        context: Optional[Union[str, Set]] = None,
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
        else:
            self.context = set(context)

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
        for (k, v) in namespace.items():
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
