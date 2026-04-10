from __future__ import annotations

import rules
from django.contrib.auth.models import AbstractUser

from voteit.agenda.models import AgendaItem

from voteit.core import PERM
from voteit.core.abcs import MeetingContext
from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived
from voteit.core.rules import is_not_finished
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_potential_voter
from voteit.meeting.rules import meeting_upcoming_ongoing
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.models import VoteTransfer
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
            # FIXME
            return user.has_perm(AgendaItem.get_perm(PERM.VIEW), poll.agenda_item)
        return user.has_perm(MeetingPermissions.VIEW, poll.meeting)
    return False


@predicate
def polls_context_not_archived(
    user: AbstractUser, instance: Poll | AgendaItem | Meeting
):
    """This is a special case where polls without agenda items are checked against meeting instead"""
    if isinstance(instance, Poll):
        if instance.agenda_item is not None:
            return is_not_archived(user, instance.agenda_item)
        return is_not_archived(user, instance.meeting)
    else:
        return is_not_archived(user, instance)


@predicate
def polls_context_not_closed(user: AbstractUser, instance: Poll | AgendaItem | Meeting):
    """This is a special case where polls without agenda items are checked against meeting instead"""
    if isinstance(instance, Poll):
        if instance.agenda_item is not None:
            return is_not_finished(user, instance.agenda_item)
        return is_not_finished(user, instance.meeting)
    else:
        return is_not_finished(user, instance)


# Poll
rules.add_perm(
    Poll.get_perm(PERM.ADD),
    is_moderator & polls_context_not_closed & polls_context_not_archived,
)  # Checked against meeting or agenda item.
rules.add_perm(Poll.get_perm(PERM.CHANGE), is_poll_in_permissive_state & is_moderator)
rules.add_perm(Poll.get_perm(PERM.DELETE), is_moderator & polls_context_not_archived)
# rules.add_perm(
#     Poll.get_perm(PERM.VIEW),
#     is_moderator | (is_not_private & can_view_polls_context),
# )
rules.add_perm(
    Poll.get_perm(PERM.CHANGE_STATE), is_moderator & polls_context_not_archived
)


@predicate
def vote_is_poll_ongoing(user: AbstractUser, vote: Vote):
    """Delegate to is_poll_ongoing"""
    return isinstance(vote, Vote) and is_poll_ongoing(user, vote.poll)


@predicate
def is_vote_transfer_enabled(user: AbstractUser, context: MeetingContext):
    return context.meeting.vote_transfer_policy is not None


@predicate
def is_transfer_source_user(user: AbstractUser, vt: VoteTransfer):
    if isinstance(vt, VoteTransfer):
        return user.pk == vt.source_id
    raise TypeError(f"{vt} is not a VoteTransfer instance")


@predicate
def is_transfer_target_user(user: AbstractUser, vt: VoteTransfer):
    if isinstance(vt, VoteTransfer):
        return user.pk == vt.target_id
    raise TypeError(f"{vt} is not a VoteTransfer instance")


# Vote
rules.add_perm(
    Vote.get_perm(PERM.ADD), is_poll_ongoing & is_voter
)  # Checked against poll.
rules.add_perm(Vote.get_perm(PERM.DELETE), is_vote_owner & vote_is_poll_ongoing)
rules.add_perm(Vote.get_perm(PERM.VIEW), is_vote_owner)


# Electoral register
rules.add_perm(ElectoralRegister.get_perm(PERM.ADD), is_moderator & is_not_archived)

# Vote transfer
rules.add_perm(
    VoteTransfer.get_perm(PERM.ADD),
    is_vote_transfer_enabled
    & meeting_upcoming_ongoing
    & (is_potential_voter | is_moderator),
)  # Checked against meeting.
rules.add_perm(
    VoteTransfer.get_perm(PERM.DELETE),
    is_vote_transfer_enabled
    & meeting_upcoming_ongoing
    & (is_transfer_source_user | is_transfer_target_user | is_moderator),
)
rules.add_perm(
    VoteTransfer.get_perm(PERM.CHANGE),
    is_vote_transfer_enabled
    & meeting_upcoming_ongoing
    & (is_transfer_source_user | is_transfer_target_user | is_moderator),
)
rules.add_perm(
    VoteTransfer.get_perm(PERM.VIEW),
    is_transfer_source_user | is_transfer_target_user | is_moderator,
)
