from __future__ import annotations

from typing import Union

import rules
from django.contrib.auth.models import AbstractUser

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived
from voteit.core.rules import is_not_finished
from voteit.core.rules import is_not_private
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.permissions import ElectoralRegisterPermissions
from voteit.poll.permissions import PollPermissions
from voteit.poll.permissions import VotePermissions
from voteit.poll.workflows import PollWf


@predicate
def is_voter(user: AbstractUser, poll: Poll):
    return (
        poll.electoral_register is not None
        and poll.electoral_register.voters.filter(pk=user.pk).exists()
    )


@predicate
def is_poll_ongoing(user: AbstractUser, poll: Poll):
    return isinstance(poll, Poll) and poll.state == PollWf.ONGOING


@predicate
def is_poll_in_permissive_state(user: AbstractUser, poll: Poll):
    return isinstance(poll, Poll) and poll.state in PollWf.permissive_states


@predicate
def is_vote_owner(user: AbstractUser, vote: Vote):
    """The person who added the vote."""
    return isinstance(vote, Vote) and vote.user == user


@predicate
def can_view_polls_context(user: AbstractUser, poll: Poll):
    """This is a special case where polls without agenda items are checked against meeting instead"""
    if isinstance(poll, Poll):
        if poll.agenda_item is not None:
            return user.has_perm(AgendaPermissions.VIEW, poll.agenda_item)
        return user.has_perm(MeetingPermissions.VIEW, poll.meeting)
    return False


@predicate
def polls_context_not_archived(
    user: AbstractUser, instance: Union[Poll, AgendaItem, Meeting]
):
    """This is a special case where polls without agenda items are checked against meeting instead"""
    if isinstance(instance, Poll):
        if instance.agenda_item is not None:
            return is_not_archived(user, instance.agenda_item)
        return is_not_archived(user, instance.meeting)
    else:
        return is_not_archived(user, instance)


@predicate
def polls_context_not_closed(
    user: AbstractUser, instance: Union[Poll, AgendaItem, Meeting]
):
    """This is a special case where polls without agenda items are checked against meeting instead"""
    if isinstance(instance, Poll):
        if instance.agenda_item is not None:
            return is_not_finished(user, instance.agenda_item)
        return is_not_finished(user, instance.meeting)
    else:
        return is_not_finished(user, instance)


# Poll
rules.add_perm(
    PollPermissions.ADD,
    is_moderator & polls_context_not_closed & polls_context_not_archived,
)  # Checked against meeting or agenda item.
rules.add_perm(PollPermissions.CHANGE, is_poll_in_permissive_state & is_moderator)
rules.add_perm(PollPermissions.DELETE, is_moderator & polls_context_not_archived)
rules.add_perm(
    PollPermissions.VIEW,
    is_moderator | (is_not_private & can_view_polls_context),
)
rules.add_perm(PollPermissions.CHANGE_STATE, is_moderator & polls_context_not_archived)


@predicate
def vote_is_poll_ongoing(user: AbstractUser, vote: Vote):
    """Delegate to is_poll_ongoing"""
    return isinstance(vote, Vote) and is_poll_ongoing(user, vote.poll)


# Vote
rules.add_perm(VotePermissions.ADD, is_poll_ongoing & is_voter)  # Checked against poll.
rules.add_perm(VotePermissions.CHANGE, is_vote_owner & vote_is_poll_ongoing)
rules.add_perm(VotePermissions.DELETE, is_vote_owner & vote_is_poll_ongoing)
rules.add_perm(VotePermissions.VIEW, is_vote_owner)


# Electoral register
rules.add_perm(ElectoralRegisterPermissions.VIEW, can_view_meeting)
rules.add_perm(ElectoralRegisterPermissions.ADD, is_moderator & is_not_archived)
