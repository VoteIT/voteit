from __future__ import annotations
from typing import TYPE_CHECKING, Union

import rules
from django.contrib.auth.models import User
from voteit.agenda.permissions import AgendaPermissions
from voteit.agenda.rules import can_moderate_agendas_meeting
from voteit.meeting.models import Meeting
from voteit.poll.abcs import Vote

from voteit.poll.models import Poll
from voteit.poll.workflows import PollWf
from voteit.poll.permissions import PollPermissions, VotePermissions
from voteit.meeting.permissions import MeetingPermissions
from voteit.agenda.models import AgendaItem

if TYPE_CHECKING:
    pass


@rules.predicate
def is_voter(user: User, poll: Poll):
    return (
        poll.electoral_register is not None
        and poll.electoral_register.voters.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_poll_ongoing(user: User, poll: Poll):
    return isinstance(poll, Poll) and poll.state == PollWf.ONGOING


@rules.predicate
def is_poll_in_permissive_state(user: User, poll: Poll):
    return isinstance(poll, Poll) and poll.state in PollWf.permissive_states


@rules.predicate
def is_not_private(user: User, poll: Poll):
    return isinstance(poll, Poll) and poll.state != PollWf.PRIVATE


@rules.predicate
def is_vote_owner(user: User, vote: Vote):
    """ The person who added the vote. """
    return isinstance(vote, Vote) and vote.user == user


# Object permissions
@rules.predicate
def can_add_poll(user: User, instance: Union[AgendaItem, Meeting]):
    """ Polls can be added either to agenda items or to meetings directly.
        This check must be able to handle both contexts with a similar result.
    """
    if isinstance(instance, AgendaItem):
        return can_moderate_agendas_meeting(user, instance)
    elif isinstance(instance, Meeting):
        return user.has_perm(MeetingPermissions.MODERATE, instance)


@rules.predicate
def can_change_poll(user: User, poll: Poll):
    # Note: Polls will always have a direct link to a meeting object,
    # so we don't need to care about the agenda item here.
    return (
        isinstance(poll, Poll)
        and is_poll_in_permissive_state(user, poll)
        and user.has_perm(MeetingPermissions.MODERATE, poll.meeting)
    )


@rules.predicate
def can_delete_poll(user: User, poll: Poll):
    """ Deleting a poll is okay in any case. Since it's very visible to users it's not as
        troubling as being able to change a poll.
    """
    return isinstance(poll, Poll) and user.has_perm(
        MeetingPermissions.MODERATE, poll.meeting
    )


@rules.predicate
def can_view_poll(user: User, poll: Poll):
    """ All participants can view a poll, there's one exception: An agenda item might be private.
        In that case it should be viewable only by moderators.
        Essentially, the same permissions as view on meeting or agenda item applies.
    """
    if isinstance(poll, Poll):
        # Simple case - the poll isn't private:
        if is_not_private(user, poll):
            # Delegate view to ai or meeting
            if isinstance(poll.agenda_item, AgendaItem):
                return user.has_perm(AgendaPermissions.VIEW, poll.agenda_item)
            return user.has_perm(MeetingPermissions.VIEW, poll.meeting)
        else:
            # To view private polls, you must be a moderator
            return user.has_perm(MeetingPermissions.MODERATE, poll.meeting)


rules.add_perm(PollPermissions.ADD, can_add_poll)  # Checked against meeting or agenda item.
rules.add_perm(PollPermissions.CHANGE, can_change_poll)
rules.add_perm(PollPermissions.DELETE, can_delete_poll)
rules.add_perm(PollPermissions.VIEW, can_view_poll)


@rules.predicate
def vote_is_poll_ongoing(user: User, vote: Vote):
    """ Delegate to is_poll_ongoing"""
    if isinstance(vote, Vote):
        try:
            poll = vote.method.poll
        except AttributeError:  # pragma: no cover
            return
        return is_poll_ongoing(user, poll)


rules.add_perm(VotePermissions.ADD, is_poll_ongoing & is_voter)  # Checked against poll.
rules.add_perm(VotePermissions.CHANGE, is_vote_owner & vote_is_poll_ongoing)
rules.add_perm(VotePermissions.DELETE, is_vote_owner & vote_is_poll_ongoing)
rules.add_perm(VotePermissions.VIEW, is_vote_owner)
