from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Model

from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.decorators import predicate
from voteit.meeting.statemachines import MeetingStateMachine

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.agenda.models import AgendaItem
    from voteit.meeting.models import MeetingGroup
    from voteit.meeting.models import Meeting
    from voteit.poll.models import Poll


_MARKER = object()


@predicate
def is_author(user: AbstractUser, instance: Model) -> bool:
    """
    Check against any generic object with the author attribute.
    """
    return getattr(instance, "author", _MARKER) == user


@predicate
def is_author_or_group_author_member(user: AbstractUser, instance: Model) -> bool:
    """
    Generic check against object with author and meeting_group attribute.
    If user isn't an author, it needs to be within the meeting group that's the author.
    """
    if is_author(user, instance):
        return True
    meeting_group: MeetingGroup | None = getattr(instance, "meeting_group", None)
    return meeting_group and user in meeting_group.members.all()


@predicate
def is_user(user: AbstractUser, instance: Model) -> bool:
    """
    Check against any generic object with the user attribute.
    """
    return getattr(instance, "user", _MARKER) == user


_ARCHIVED_STATES = (
    MeetingStateMachine.archived_states | AgendaItemStateMachine.archived_states
)


@predicate
def is_not_archived(user: AbstractUser, instance: Meeting | AgendaItem) -> bool:
    """
    Generic check for archived state.
    Keep this as a negated state since check for is not None will return a false positive otherwise!
    """
    state = getattr(instance, "state", None)
    return state is not None and state not in _ARCHIVED_STATES


_FINISHED_STATES = (
    MeetingStateMachine.finished_states | AgendaItemStateMachine.finished_states
)


@predicate
def is_not_finished(user: AbstractUser, instance: Meeting | AgendaItem) -> bool:
    """
    The meeting/agenda item is not closed, archived etc.
    Agenda items may be private too
    """
    state = getattr(instance, "state", None)
    return state is not None and state not in _FINISHED_STATES


@predicate
def is_not_private(user: AbstractUser, instance: AgendaItem | Poll) -> bool:
    """
    Checked against any object that has a state.
    """
    state = getattr(instance, "state", None)
    return state not in [None, "private"]
