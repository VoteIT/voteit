from __future__ import annotations

import os
from collections import UserDict
from collections import defaultdict
from itertools import chain
from logging import getLogger
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.module_loading import import_string
from pydantic import BaseModel
from typing import Generator
from yaml import safe_load

from voteit.components.app.components.dialects import DialectsFilter
from voteit.core.decorators import ensure_atomic
from voteit.core.workflows import EnabledWf
from voteit.meeting.exceptions import DialectError
from voteit.meeting.models import Meeting
from voteit.meeting.schemas import DialectSchema

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation

logger = getLogger(__name__)


def refresh(method):
    """
    This is a somewhat silly method of refreshing data.
    Replace it with saner caching invalidation later on.
    We don't need to bother with caching right now since we have very few dialects
    """

    def inner(ref: DialectRegistry, *args, **kwargs):
        ref.data.clear()
        for name, path in get_named_paths():
            ref[name] = DialectHandler.load_from_file(name, path)
        return method(ref, *args, **kwargs)

    return inner


class DialectRegistry(UserDict):
    """
    Manages dialects
    """

    data: dict[str, DialectHandler]

    @refresh
    def load(self): ...

    @refresh
    def get_installable(self, include=tuple(), exclude=tuple()) -> dict[str, str]:
        """
        Return installable dialects
        """
        results = {}
        for k, v in self.items():
            if k in exclude:
                continue
            if k in include or v.data.installable:
                results[k] = v.data.title or k
        return results

    @refresh
    def get_dependent_dialects(self, name: str) -> list[DialectHandler]:
        """
        Returns any required dialects with the name specified first.
        Requirements should be installed in the reverse order!
        """
        added_names = set()
        return_names = [name]
        results = []
        while return_names:
            current = return_names.pop(0)
            if current in added_names:
                raise DialectError(
                    f"While loading {name}, the dialect name {current} seems to be part of a cyclic dependency."
                )
            added_names.add(current)
            handler = self[current]
            results.append(handler)
            if handler.data.requires:
                return_names.extend(handler.data.requires)
        return results

    def get_title(self, name: str, default=None) -> str | None:
        if name in self:
            return self[name].data.title or name
        return default

    def get_merged_handler(self, name) -> DialectHandler:
        """
        Load a dialect handler + any requirements and merge the required dialects data into the first one.
        Preserves nested data, at least one lever deep :P
        """
        data = {}
        for handler in reversed(self.get_dependent_dialects(name)):
            handler_data = handler.data.dict(
                exclude_none=True,
            )
            for k in _dialect_schema_list_items:
                items = handler_data.pop(k, None)
                if items:
                    if k not in data:
                        data[k] = []
                    data[k].extend(i for i in items if i not in data[k])
            data.update(handler_data)
        data["name"] = name
        return DialectHandler.load_from_dict(data)

    def get_org_installable(self, organisation: Organisation | None):
        kwargs = {}
        if organisation:
            component = organisation.components.filter(
                component_name=DialectsFilter.name
            ).first()
            if component:
                kwargs["include"] = component.settings.include
                kwargs["exclude"] = component.settings.exclude
        return self.get_installable(**kwargs)


dialect_registry = DialectRegistry()


def get_named_paths() -> Generator[tuple[str, str]]:
    dialects_dir = getattr(settings, "MEETING_DIALECTS_DIR", None)
    if dialects_dir is None:
        logger.warning("Missing MEETING_DIALECTS_DIR settings, can't load dialects.")
    else:
        for root, dirs, files in os.walk(dialects_dir):
            for fname in files:
                parts = fname.split(".")
                if parts[-1] not in {"yaml", "yml"}:
                    continue
                yield ".".join(parts[:-1]), os.path.join(root, fname)


class DialectHandler:
    data: DialectSchema
    schema = DialectSchema
    optional_nullable = (
        "er_policy_name",
        "proposal_id_policy_name",
    )
    optional_default_false = (
        "group_votes_active",
        "group_roles_active",
    )

    def __init__(self, data: DialectSchema):
        self.data = data

    @classmethod
    def load_from_dict(cls, data: dict) -> DialectHandler:
        data = cls.schema(**data)
        return cls(data)

    @classmethod
    def load_from_file(cls, name: str, path: str) -> DialectHandler:
        with open(path, "r") as f:
            data = safe_load(f)
        if not isinstance(data, dict):
            raise TypeError(
                f"Loading dialect file {path} returned data that wasn't a dict"
            )
        data["name"] = name
        return cls.load_from_dict(data)

    @ensure_atomic
    def install(self, meeting: Meeting):
        # Basics
        if meeting.installed_dialect:
            raise DialectError(f"Meeting already has an installed dialect")
        meeting.installed_dialect = self.data.name
        # Optionals
        for k in chain(self.optional_nullable, self.optional_default_false):
            v = getattr(self.data, k)
            if v is not None:
                setattr(meeting, k, v)
        meeting.save()
        # Block components
        if self.data.block_components:
            for component in meeting.components.filter(
                component_name__in=self.data.block_components,
                state=EnabledWf.ON,
            ):
                component.disable()
                component.save()
        # Configure components
        for cs in self.data.configure_components:
            # Reset component to trigger validation on state change
            component, _ = meeting.components.update_or_create(
                component_name=cs.name,
                defaults={"settings_data": cs.settings, "state": EnabledWf.OFF},
            )
            component.enable()
            component.save()
        # GroupRoles
        for gr_data in self.data.roles:
            group_role = meeting.group_roles.filter(role_id=gr_data.role_id).first()
            if group_role is None:
                meeting.group_roles.create(**gr_data.dict())
            else:
                for k, v in gr_data.dict(exclude={"role_id"}).items():
                    if getattr(group_role, k, object()) != v:
                        setattr(group_role, k, v)
                group_role.save()
        # Groups
        for g_data in self.data.groups:
            group = meeting.groups.filter(groupid=g_data.groupid).first()
            if group is None:
                meeting.groups.create(**g_data.dict())
            else:
                for k, v in g_data.dict(exclude={"groupid"}).items():
                    if getattr(group, k, object()) != v:
                        setattr(group, k, v)
                group.save()
        # And install scripts
        for script in self.load_dialect_scripts():
            script.install(meeting)

    @ensure_atomic
    def remove(self, meeting: Meeting, groups: bool = False):
        if self.data.name != meeting.installed_dialect:
            raise DialectError("%s is not installed" % self.data.name)
        meeting.installed_dialect = None
        # Optional, only touch not none
        # Always disable these if they had a setting
        for k in self.optional_default_false:
            v = getattr(self.data, k)
            if v is not None:
                setattr(meeting, k, False)
        # And these should be removed if they existed
        for k in self.optional_nullable:
            v = getattr(self.data, k)
            if v is not None:
                setattr(meeting, k, None)
        meeting.save()
        # GroupRoles
        meeting.group_roles.filter(
            role_id__in=[x.role_id for x in self.data.roles]
        ).delete()
        if groups:
            meeting.groups.filter(
                groupid__in=[x.groupid for x in self.data.groups]
            ).delete()
        # Any remove or cleanup?
        for script in self.load_dialect_scripts():
            script.remove(meeting)

    def load_dialect_scripts(self) -> list[DialectScript]:
        # This could've been a generator, but we want to validate all before running
        results = []
        for mod_path in self.data.run_scripts:
            try:
                klass = import_string(mod_path)
            except ImportError as exc:
                raise ValueError(
                    f"Error when processing meeting dialect {self.data.name} run_scripts: {str(exc)}"
                )
            if not isinstance(klass, type) or not issubclass(klass, DialectScript):
                raise TypeError(
                    f"Error when processing meeting dialect {self.data.name} "
                    f"run_scripts: {mod_path} is not a subclass of DialectScript"
                )
            results.append(klass(self))
        return results


def check_dialect_files() -> list[tuple[str, str]]:
    """
    Check files during tests
    >>> _ = check_dialect_files()
    """
    intra_req_checks = defaultdict(set)
    names_titles = []
    for name, path in get_named_paths():
        handler = DialectHandler.load_from_file(name, path)
        intra_req_checks[name].update(handler.data.requires)
        names_titles.append((name, handler.data.title))
        # Validate, we don't need to do anything
        handler.load_dialect_scripts()
    # It doesn't check cyclic, so let's hope that doesn't happen ;)
    for name, reqs in intra_req_checks.items():
        for req in reqs:
            if req not in intra_req_checks:
                raise DialectError(
                    f"Dialect {name} specifies a requirement to 'req' but it doesn't exist."
                )
    return names_titles


def _get_schema_list_items(schema_cls: type[BaseModel]) -> set[str]:
    return {
        k
        for k, v in schema_cls.schema()["properties"].items()
        if v.get("type") == "array"
    }


_dialect_schema_list_items = _get_schema_list_items(DialectSchema)


class DialectScript:
    def __init__(self, handler: DialectHandler):
        self.handler = handler

    def install(self, meeting: Meeting): ...

    def remove(self, meeting: Meeting): ...
