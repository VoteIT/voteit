from __future__ import annotations
from typing import Union, TYPE_CHECKING

from django.db.models import Model
from voteit.agenda.workflows import AgendaItemWf
from voteit.meeting.workflows import MeetingWf
from voteit.core.decorators import predicate

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.agenda.models import AgendaItem
    from voteit.meeting.models import Meeting
    from voteit.poll.models import Poll


_MARKER = object()


@predicate
def is_author(user: AbstractUser, instance: Model) -> bool:
    """ Check against any generic object with the author attribute. """
    return getattr(instance, "author", _MARKER) == user


@predicate
def is_user(user: AbstractUser, instance: Model) -> bool:
    """ Check against any generic object with the user attribute. """
    return getattr(instance, "user", _MARKER) == user


_ARCHIVED_STATES = MeetingWf.archived_states | AgendaItemWf.archived_states


@predicate
def is_not_archived(user: AbstractUser, instance: Union[Meeting, AgendaItem]) -> bool:
    """Generic check for archived state.
    Keep this as a negated state since check for is not None will return a false positive otherwise!
    """
    state = getattr(instance, "state", None)
    return state is not None and state not in _ARCHIVED_STATES


_FINISHED_STATES = MeetingWf.finished_states | AgendaItemWf.finished_states


@predicate
def is_not_finished(user: AbstractUser, instance: Union[Meeting, AgendaItem]) -> bool:
    """The meeting/agenda item is not closed, archived etc.
    Agenda items may be private too
    """
    state = getattr(instance, "state", None)
    return state is not None and state not in _FINISHED_STATES


@predicate
def is_not_private(user: AbstractUser, instance: Union[AgendaItem, Poll]) -> bool:
    """ Checked against any object that has a state."""
    state = getattr(instance, "state", None)
    return state not in [None, "private"]
