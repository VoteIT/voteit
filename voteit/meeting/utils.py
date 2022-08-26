from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING
from typing import Type

from django.contrib.contenttypes.models import ContentType
from django_fsm import FSMField
from dolly.core import LiveCloner
from dolly.utils import get_inf_collector
from dolly.utils import get_model_formatted_dict

from voteit.core.decorators import ensure_atomic
from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_by_shortname
from voteit.meeting.roles import ROLE_MODERATOR

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.core.models import User
    from django.db.models import Model

logger = getLogger(__name__)


def collect_meeting(meeting: Meeting, exclude: list[Type[Model]] = ()):
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


def get_default_models_ignored_on_clone() -> set[Type[Model]]:
    """
    >>> items = get_default_models_ignored_on_clone()
    >>> None not in items
    True
    """
    ignore = set(get_model_by_shortname(x) for x in get_default_ignored_on_clone())
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
