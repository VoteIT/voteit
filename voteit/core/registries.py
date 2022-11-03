from __future__ import annotations

from typing import Generator
from typing import TYPE_CHECKING

from django.db.models import Model
from rules import Predicate

from voteit.core.component import Registry
from voteit.core.permissions import Permission
from voteit.core.predicate import PredicateRegistry
from voteit.core.utils import get_model_by_shortname

if TYPE_CHECKING:
    from voteit.core.permissions import ModelPermissions


class ContentRegistry(Registry):
    """Stores content types and handles naming.
    Any model that's ready should be present here

    >>> content_types["meeting"]
    <class 'voteit.meeting.models.Meeting'>

    Natural key can be looked up via this registry too
    By str
    >>> content_types.get_natural_key("agenda_item")
    'agenda.agendaitem'

    By instance or class
    >>> from voteit.meeting.models import Meeting
    >>> content_types.get_natural_key(Meeting)
    'meeting.meeting'
    >>> content_types.get_natural_key(Meeting())
    'meeting.meeting'

    We've also added the User method here as user regardless of where it comes from
    >>> from django.contrib.auth import get_user_model
    >>> User = get_user_model()
    >>> "user" in content_types
    True
    >>> content_types["user"] is User
    True
    """

    def get_natural_key(self, obj: str | Model | type[Model]) -> str:
        if isinstance(obj, str):
            obj = self[obj]
        if isinstance(obj, Model):
            obj = obj.__class__
        return f"{obj._meta.app_label}.{obj._meta.model_name.lower()}"


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

    def __init__(self, required):
        super().__init__(required)
        self.model_permissions = {}  # Relations to actual model permissions

    def get_model_permissions(self, name) -> ModelPermissions:
        return self.model_permissions[name]

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


predicates = PredicateRegistry(Predicate)
permissions = PermissionRegistry(Permission)
content_types = ContentRegistry(Model)
