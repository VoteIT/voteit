from __future__ import annotations

import os
from itertools import chain
from logging import getLogger
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django_fsm import FSMField
from yaml import safe_load

from dolly.core import LiveCloner
from dolly.utils import get_inf_collector
from dolly.utils import get_model_formatted_dict

from voteit.core.decorators import ensure_atomic
from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_by_shortname
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
        "presence_system",
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


class DialectHandler:
    registry: dict[str, str] = {}  # name as k, full filepath as v
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
    def populate_registry(cls):
        dialects_dir = getattr(settings, "MEETING_DIALECTS_DIR", None)
        if dialects_dir is None:
            logger.warning(
                "Missing MEETING_DIALECTS_DIR settings, can't load dialects."
            )
            return
        for root, dirs, files in os.walk(dialects_dir):
            for fname in files:
                parts = fname.split(".")
                if parts[-1] not in {"yaml", "yml"}:
                    logger.warning("Skipping dialect file %s, must be yaml", fname)
                name = ".".join(parts[:-1])
                fullpath = os.path.join(root, fname)
                # Make sure data works
                with open(fullpath, "r") as f:
                    data = safe_load(f)
                if not isinstance(data, dict):
                    logger.exception(
                        "Loading dialect file %s returned data that wasn't a dict",
                        fname,
                    )
                    continue
                data["name"] = name
                try:
                    cls.schema(**data)
                except ValueError:
                    logger.exception(
                        "Loading dialect file %s caused suppressed exception - file skipped",
                        fname,
                    )
                    continue
                cls.registry[name] = fullpath

    @classmethod
    def load_from_dict(cls, data: dict):
        data = cls.schema(**data)
        return cls(data)

    @classmethod
    def load_from_name(cls, name: str):
        with open(cls.registry[name], "r") as f:
            data = safe_load(f)
        # Default to filename
        data["name"] = name
        return cls.load_from_dict(data)

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
