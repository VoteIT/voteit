from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.functions import Collate
# from dolly.core import LiveCloner
# from dolly.utils import get_inf_collector
# from dolly.utils import get_model_formatted_dict

from voteit.core.utils import get_model_by_shortname

if TYPE_CHECKING:
    from django.db.models import Model
    from voteit.meeting.models import Meeting
    from voteit.agenda.models import AgendaItem

logger = getLogger(__name__)


# def collect_meeting(meeting: Meeting, *, exclude: list[type[Model]] = ()):
#     content_reg = get_content_registry()
#     collector = get_inf_collector()
#     collector.EXCLUDE_MODELS = []
#     for m in exclude:
#         nat_key = content_reg.get_natural_key(m)
#         if not nat_key:
#             raise ValueError(f"{m} got bad natural key")
#         collector.EXCLUDE_MODELS.append(nat_key)
#     collector.collect(meeting)
#     related_objects = collector.get_collected_objects()
#     return get_model_formatted_dict(related_objects)


def get_default_ignored_on_clone() -> set[str]:
    """
    Fetch shortnames that should (probably) be ignored when you clone a meeting.
    """
    return {
        "electoral_register",
        "last_read",
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
    ignore = set()
    for shortname in get_default_ignored_on_clone():
        model = get_model_by_shortname(shortname)
        if model:
            ignore.add(model)
        else:
            logger.warning(f"{shortname} returned no model")
    ignore.add(ContentType)
    return ignore


class _WFResetter:
    def __init__(self, fields):
        self.fields = fields

    def __call__(self, cloner, *objs):
        for field in self.fields:
            for obj in objs:
                field.set_state(obj, field.default)


# @ensure_atomic
# def clone_meeting(
#     meeting: Meeting,
#     exclude=None,
#     *,
#     user: User,
#     prefix: str = "Copy of",
#     reset_wf: bool = True,
# ) -> Meeting:
#     """
#     Clone meeting and return the newly cloned. Will also add cloning user as moderator.
#
#     """
#     from voteit.meeting.models import Meeting
#     from voteit.meeting.roles import ROLE_MODERATOR
#     from voteit.speaker.models import SpeakerListSystem
#     from voteit.room.models import Room
#
#     assert user is not None
#     if exclude is None:
#         exclude = get_default_models_ignored_on_clone()
#     data = collect_meeting(meeting, exclude=exclude)
#     cloner = LiveCloner(data=data)
#     # This should never be copied
#     cloner.add_clear_attrs(SpeakerListSystem, "active_list")
#     cloner.add_clear_attrs(Meeting, "participants")
#     cloner.add_clear_attrs(Room, "agenda_item", "handler", "poll")
#     if reset_wf:
#         for mod in cloner.data:
#             wf_fields = set()
#             for field in mod._meta.get_fields():
#                 if isinstance(field, FSMField):
#                     wf_fields.add(field)
#             if wf_fields:
#                 resetter = _WFResetter(wf_fields)
#                 cloner.add_pre_save(mod, resetter)
#     cloner()
#     # Note: Meeting is now the clone!!!
#     if prefix:
#         meeting.title = f"{prefix} {meeting.title}"[:100]
#         meeting.save()
#     if user.organisation == meeting.organisation:
#         meeting.add_roles(user, ROLE_MODERATOR)
#     else:
#         logger.warning(
#             f"User {user} doesn't belong to organisation {meeting.organisation} so that user won't be added as moderator."
#         )
#     return meeting


def sort_agenda_items(
    meeting: Meeting, locale_name: str = "sv-x-icu", reorder=False
) -> models.QuerySet[AgendaItem]:
    qs = meeting.agenda_items.order_by(Collate(models.F("title"), locale_name))
    if reorder:
        for i, ai in enumerate(qs, 1):
            if ai.order != i:
                ai.order = i
                ai.save()
    return qs
