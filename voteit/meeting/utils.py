from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Type

from dolly.core import LiveCloner
from dolly.utils import get_inf_collector
from dolly.utils import get_model_formatted_dict

from voteit.core.decorators import ensure_atomic
from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_by_shortname

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from django.db.models import Model


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
    Fetch names that should (probably) be ignored when you clone a meeting.

    """
    return {
        "electoral_register",
        "meeting_roles",
        "organisation",
        "poll",
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
    return set(get_model_by_shortname(x) for x in get_default_ignored_on_clone())


@ensure_atomic
def clone_meeting(meeting: Meeting, exclude=None) -> Meeting:
    if exclude is None:
        exclude = get_default_models_ignored_on_clone()
    data = collect_meeting(meeting, exclude=exclude)
    cloner = LiveCloner(data=data)
    cloner()
    return meeting  # Note: Meeting is now the clone!!!
