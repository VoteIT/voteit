from __future__ import annotations
from typing import Union, TYPE_CHECKING

import rules
from django.contrib.auth.models import AbstractUser
from django.db.models import Model
from voteit.agenda.workflows import AgendaItemWf
from voteit.meeting.workflows import MeetingWf

if TYPE_CHECKING:
    from voteit.agenda.models import AgendaItem
    from voteit.meeting.models import Meeting


_MARKER = object()


@rules.predicate
def is_author(user: AbstractUser, instance: Model):
    """ Check against any generic object with the author attribute. """
    return getattr(instance, "author", _MARKER) == user


_ARCHIVED_STATES = MeetingWf.archived_states | AgendaItemWf.archived_states


@rules.predicate
def is_not_archived(user: AbstractUser, instance: Union[Meeting, AgendaItem]):
    """ Generic check for archived state.
        Keep this as a negated state since check for is not None will return a false positive otherwise!
    """
    state = getattr(instance, "state", None)
    return state is not None and state not in _ARCHIVED_STATES


_FINISHED_STATES = MeetingWf.finished_states | AgendaItemWf.finished_states


@rules.predicate
def is_not_finished(user: AbstractUser, instance: Union[Meeting, AgendaItem]):
    """ The meeting/agenda item is not closed, archived etc.
        Agenda items may be private too
    """
    state = getattr(instance, "state", None)
    return state is not None and state not in _FINISHED_STATES
