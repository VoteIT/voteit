from __future__ import annotations

from typing import TYPE_CHECKING

import rules
from django.contrib.auth.models import AbstractUser
from rules import is_authenticated

from voteit.core import PERM
from voteit.core.abcs import MeetingContext
from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived
from voteit.meeting import PERM_CHANGE_DIALECT
from voteit.meeting import PERM_PREVIEW
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.statemachines import MeetingStateMachine
from voteit.organisation.rules import is_manager
from voteit.organisation.rules import is_meeting_creator

if TYPE_CHECKING:
    pass


@predicate(role=ROLE_PARTICIPANT)
def is_participant(user: AbstractUser, context: MeetingContext) -> bool:
    """
    Is this a meeting participant? (Any kind of role)
    """
    if not isinstance(context, MeetingContext):
        raise TypeError(f"Expected MeetingContext, got {type(context)}")
    meeting_id = getattr(context, "meeting_id", context.meeting.pk)
    return MeetingRoles.objects.filter(context_id=meeting_id, user=user).exists()


@predicate(role=ROLE_POTENTIAL_VOTER)
def is_potential_voter(user: AbstractUser, context: MeetingContext) -> bool:
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.has_roles(user, ROLE_POTENTIAL_VOTER)
    )


@predicate(role=ROLE_MODERATOR)
def is_moderator(user: AbstractUser, context: MeetingContext) -> bool:
    """
    Note that this method isn't negatable!
    """
    if not isinstance(context, MeetingContext):
        return False
    return context.meeting is not None and context.meeting.has_roles(
        user, ROLE_MODERATOR
    )


@predicate(role=ROLE_DISCUSSER)
def is_discusser(user: AbstractUser, context: MeetingContext) -> bool:
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.has_roles(user, ROLE_DISCUSSER)
    )


@predicate(role=ROLE_PROPOSER)
def is_proposer(user: AbstractUser, context: MeetingContext) -> bool:
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.has_roles(user, ROLE_PROPOSER)
    )


@predicate
def is_public_meeting(user: AbstractUser, context: MeetingContext) -> bool:
    """The meeting is visible for everyone."""
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.public
    )


@predicate
def meeting_not_archived(user: AbstractUser, context: MeetingContext) -> bool:
    """The related meeting isn't archived or archiving."""
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and is_not_archived(user, context.meeting)
    )


@predicate
def meeting_not_fully_archived(user: AbstractUser, context: MeetingContext) -> bool:
    """
    Special case for archiving controls. If a meeting is in the state archiving, the process can be aborted.
    This should not be used for something other than the archive-permission.
    """
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.state != MeetingStateMachine.archived.value
    )


@predicate
def meeting_upcoming_ongoing(user: AbstractUser, context: MeetingContext) -> bool:
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.state
        in (MeetingStateMachine.ongoing.value, MeetingStateMachine.upcoming.value)
    )


@predicate
def meeting_upcoming(user: AbstractUser, context: MeetingContext) -> bool:
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.state == MeetingStateMachine.upcoming.value
    )


@predicate
def can_view_meeting(user: AbstractUser, context: MeetingContext) -> bool:
    """
    Shorthand for the combinations to allow attached meeting to be viewed.
    Import and use this for any underlying things that implement MeetingContext
    """
    return is_authenticated(user) and (
        is_public_meeting(user, context) or is_participant(user, context)
    )


@predicate
def visible_in_lists(user: AbstractUser, context: MeetingContext) -> bool:
    """
    Allow meeting to be included in basic listings. For instance details like how many proposals, basic intro, title etc.
    No sensitive information of course.
    """
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.visible_in_lists
    )


rules.add_perm(Meeting.get_perm(PERM.ADD), is_meeting_creator)
# FIXME: This queryset has changed. It used to include public meetings
rules.add_perm(Meeting.get_perm(PERM.VIEW), is_participant)
rules.add_perm(Meeting.get_perm(PERM.MODERATE), is_moderator)
rules.add_perm(
    Meeting.get_perm(PERM.ARCHIVE), meeting_not_fully_archived & is_moderator
)
# We might want to add editor role later on
rules.add_perm(Meeting.get_perm(PERM.CHANGE), meeting_not_archived & is_moderator)
rules.add_perm(Meeting.get_perm(PERM_CHANGE_DIALECT), meeting_upcoming & is_moderator)
rules.add_perm(Meeting.get_perm(PERM.DELETE), is_moderator)
rules.add_perm(
    Meeting.get_perm(PERM.CHANGE_ROLES),
    meeting_not_archived & (is_moderator | is_manager),
)
rules.add_perm(Meeting.get_perm(PERM_PREVIEW), visible_in_lists)
# FIXME: View should be removed here, use queryset instead. Fix when messages update.
rules.add_perm(Meeting.get_perm(PERM.VIEW_ROLES), is_participant)

rules.add_perm(MeetingGroup.get_perm(PERM.ADD), meeting_not_archived & is_moderator)
rules.add_perm(MeetingGroup.get_perm(PERM.CHANGE), meeting_not_archived & is_moderator)
rules.add_perm(MeetingGroup.get_perm(PERM.DELETE), meeting_not_archived & is_moderator)
# Used by messages
rules.add_perm(MeetingGroup.get_perm(PERM.VIEW), is_participant)
rules.add_perm(GroupMembership.get_perm(PERM.ADD), meeting_not_archived & is_moderator)
rules.add_perm(
    GroupMembership.get_perm(PERM.CHANGE), meeting_not_archived & is_moderator
)
rules.add_perm(
    GroupMembership.get_perm(PERM.DELETE), meeting_not_archived & is_moderator
)
