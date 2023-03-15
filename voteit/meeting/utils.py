from __future__ import annotations

import os
from collections import defaultdict
from itertools import chain
from logging import getLogger
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django_fsm import FSMField
from pydantic import BaseModel
from dolly.core import LiveCloner
from dolly.utils import get_inf_collector
from dolly.utils import get_model_formatted_dict
from yaml import safe_load

from voteit.core.decorators import ensure_atomic
from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_by_shortname
from voteit.core.workflows import EnabledWf
from voteit.meeting.exceptions import DialectError
from voteit.meeting.schemas import DialectSchema

if TYPE_CHECKING:
    from django.db.models import Model
    from voteit.meeting.models import Meeting
    from voteit.core.models import User

logger = getLogger(__name__)


def collect_meeting(meeting: Meeting, exclude: list[type[Model]] = ()):
    content_reg = get_content_registry()
    collector = get_inf_collector()
    collector.EXCLUDE_MODELS = []
    for m in exclude:
        collector.EXCLUDE_MODELS.append(content_reg.get_natural_key(m))
    collector.collect(meeting)
    related_objects = collector.get_collected_objects()
    return get_model_formatted_dict(related_objects)


def get_default_ignored_on_clone() -> set[str]:
    """
    Fetch shortnames that should (probably) be ignored when you clone a meeting.
    """
    return {
        "bug_report",
        "electoral_register",
        "last_read",
        "invite_dispatch",
        "meeting_invite",
        "meeting_roles",
        "organisation",
        "poll",
        "pnsystem",
        "presence",
        "presence_check",
        "reaction",
        "speaker",
        "speaker_list",
        "speaker_roles",
        "text_paragraph",  # Made automatically by text_doc
        "user",
        "vote",
        "voter_weight",
    }


def get_default_models_ignored_on_clone() -> set[type[Model]]:
    """
    >>> items = get_default_models_ignored_on_clone()
    >>> None not in items
    True
    """
    ignore = {get_model_by_shortname(x) for x in get_default_ignored_on_clone()}
    ignore.add(ContentType)
    return ignore


class _WFResetter:
    def __init__(self, fields):
        self.fields = fields

    def __call__(self, cloner, *objs):
        for field in self.fields:
            for obj in objs:
                field.set_state(obj, field.default)


@ensure_atomic
def clone_meeting(
    meeting: Meeting,
    exclude=None,
    user: User = None,
    prefix: str = "Copy of",
    reset_wf: bool = True,
) -> Meeting:
    """
    Clone meeting and return the newly cloned. Will also add cloning user as moderator.

    """
    from voteit.meeting.models import Meeting
    from voteit.meeting.roles import ROLE_MODERATOR
    from voteit.speaker.models import SpeakerListSystem

    assert user is not None
    if exclude is None:
        exclude = get_default_models_ignored_on_clone()
    data = collect_meeting(meeting, exclude=exclude)
    cloner = LiveCloner(data=data)
    # This should never be copied
    cloner.add_clear_attrs(SpeakerListSystem, "active_list")
    cloner.add_clear_attrs(Meeting, "participants")
    if reset_wf:
        for mod in cloner.data:
            wf_fields = set()
            for field in mod._meta.get_fields():
                if isinstance(field, FSMField):
                    wf_fields.add(field)
            if wf_fields:
                resetter = _WFResetter(wf_fields)
                cloner.add_pre_save(mod, resetter)
    cloner()
    # Note: Meeting is now the clone!!!
    if prefix:
        meeting.title = f"{prefix} {meeting.title}"[:100]
        meeting.save()
    if user.organisation == meeting.organisation:
        meeting.add_roles(user, ROLE_MODERATOR)
    else:
        logger.warning(
            f"User {user} doesn't belong to organisation {meeting.organisation} so that user won't be added as moderator."
        )
    return meeting


def check_dialect_files() -> list[tuple[str, str]]:
    """
    Check files during tests
    >>> _ = check_dialect_files()
    """
    intra_req_checks = defaultdict(set)
    named_paths = get_named_path_dict()
    names_titles = []

    for name, path in named_paths.items():
        data_model = load_dialect_file(name, path)
        intra_req_checks[name].update(data_model.data.requires)
        names_titles.append((name, data_model.data.title))

    # It doesn't check cyclic, so let's hope that doesn't happen ;)
    for name, reqs in intra_req_checks.items():
        for req in reqs:
            if req not in intra_req_checks:
                raise DialectError(
                    f"Dialect {name} specifies a requirement to 'req' but it doesn't exist."
                )
    return names_titles


def get_named_path_dict() -> dict[str, str]:
    results = {}
    dialects_dir = getattr(settings, "MEETING_DIALECTS_DIR", None)
    if dialects_dir is None:
        logger.warning("Missing MEETING_DIALECTS_DIR settings, can't load dialects.")
        return results
    for root, dirs, files in os.walk(dialects_dir):
        for fname in files:
            parts = fname.split(".")
            if parts[-1] not in {"yaml", "yml"}:
                continue
            name = ".".join(parts[:-1])
            results[name] = os.path.join(root, fname)
    return results


# FIXME: LRU-Cache for dialects?
def load_dialect_file(name: str, path: str) -> DialectHandler:
    with open(path, "r") as f:
        data = safe_load(f)
    if not isinstance(data, dict):
        raise TypeError(f"Loading dialect file {path} returned data that wasn't a dict")
    data["name"] = name
    return DialectHandler.load_from_dict(data)


def recursive_load_handlers(
    name: str,
    loaded_names: list[str] | None = None,
    named_paths: dict[str, str] | None = None,
    handlers: list[DialectHandler] | None = None,
) -> list[DialectHandler]:
    if named_paths is None:
        named_paths = get_named_path_dict()
    if loaded_names is None:
        loaded_names = []
    if name in loaded_names:
        raise DialectError(f"Cyclic dependency, dialect {name} already loaded")
    if handlers is None:
        handlers = []
    if name not in named_paths:
        raise DialectError(f"Dialect {name} doesn't exist or has invalid data")
    handler = load_dialect_file(name, named_paths[name])
    handlers.insert(0, handler)
    loaded_names.append(name)
    for req in handler.data.requires:
        recursive_load_handlers(
            req, loaded_names=loaded_names, named_paths=named_paths, handlers=handlers
        )
    return handlers


def _get_schema_list_items(schema_cls: type[BaseModel]) -> set[str]:
    return {
        k
        for k, v in schema_cls.schema()["properties"].items()
        if v.get("type") == "array"
    }


_dialect_schema_list_items = _get_schema_list_items(DialectSchema)


def get_merged_dialect_data(only=None) -> dict[str, dict]:
    """
    Any installable dialects that require other non-installable should contain
    that data too, so frontend only has to care about the specific dialect in question.
    """
    # FIXME: This may need to be cached

    dialect_handlers = {}
    named_paths = get_named_path_dict()
    for name in named_paths:
        if only and name != only:
            continue
        handlers = recursive_load_handlers(name, named_paths=named_paths)
        if handlers[-1].data.installable or name == only:
            # merge data
            data = {}
            for handler in handlers:
                handler_data = handler.data.dict(exclude_none=True)
                for k in _dialect_schema_list_items:
                    items = handler_data.pop(k, None)
                    if items:
                        if k not in data:
                            data[k] = []
                        data[k].extend(i for i in items if i not in data[k])
                data.update(handler_data)
            dialect_handlers[name] = data
    return dialect_handlers


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
    def load_from_dict(cls, data: dict):
        data = cls.schema(**data)
        return cls(data)

    @ensure_atomic
    def install(self, meeting: Meeting):
        # Basics
        installed = (
            meeting.installed_dialects and meeting.installed_dialects.split(",") or []
        )
        if self.data.name in installed:
            raise DialectError(f"{self.data.name} already installed")
        for req in self.data.requires:
            if req not in installed:
                raise DialectError(
                    f"{req} must be installed before installing {self.data.name}"
                )
        installed.append(self.data.name)
        meeting.installed_dialects = ",".join(installed)
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

    @ensure_atomic
    def remove(self, meeting: Meeting):
        installed = (
            meeting.installed_dialects and meeting.installed_dialects.split(",") or []
        )
        if self.data.name not in installed[-1:]:
            raise DialectError("%s is not the last installed dialect" % self.data.name)
        installed.remove(self.data.name)
        if installed:
            meeting.installed_dialects = ",".join(installed)
        else:
            meeting.installed_dialects = None
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
        # Groups
        meeting.groups.filter(
            groupid__in=[x.groupid for x in self.data.groups]
        ).delete()
