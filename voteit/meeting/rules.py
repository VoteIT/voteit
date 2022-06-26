from __future__ import annotations

from typing import TYPE_CHECKING

import rules
from django.contrib.auth.models import AbstractUser
from rules import is_authenticated

from voteit.core.abcs import MeetingContext
from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived
from voteit.meeting.permissions import MeetingGroupPermissions
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.workflows import MeetingWf
from voteit.organisation.rules import is_manager
from voteit.organisation.rules import is_meeting_creator

if TYPE_CHECKING:
    pass


@predicate(role=ROLE_PARTICIPANT)
def is_participant(user: AbstractUser, context: MeetingContext) -> bool:
    """Is this a meeting participant?"""
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.has_roles(user, ROLE_PARTICIPANT)
    )


@predicate(role=ROLE_POTENTIAL_VOTER)
def is_potential_voter(user: AbstractUser, context: MeetingContext) -> bool:
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.has_roles(user, ROLE_POTENTIAL_VOTER)
    )


@predicate(role=ROLE_MODERATOR)
def is_moderator(user: AbstractUser, context: MeetingContext) -> bool:
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.has_roles(user, ROLE_MODERATOR)
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
        and context.meeting.state != MeetingWf.ARCHIVED
    )


@predicate
def meeting_upcoming_ongoing(user: AbstractUser, context: MeetingContext) -> bool:
    return (
        isinstance(context, MeetingContext)
        and context.meeting is not None
        and context.meeting.state in (MeetingWf.ONGOING, MeetingWf.UPCOMING)
    )


@predicate
def can_view_meeting(user: AbstractUser, context: MeetingContext) -> bool:
    """Shorthand for the combinations to allow attached meeting to be viewed.
    Import and use this for any underlying things that implement MeetingContext
    """
    return is_authenticated(user) and (
        is_public_meeting(user, context)
        or is_participant(user, context)
        or is_moderator(user, context)
    )


rules.add_perm(MeetingPermissions.ADD, is_manager | is_meeting_creator)
rules.add_perm(MeetingPermissions.VIEW, can_view_meeting)
rules.add_perm(MeetingPermissions.MODERATE, meeting_not_archived & is_moderator)
rules.add_perm(MeetingPermissions.ARCHIVE, meeting_not_fully_archived & is_moderator)
# We might want to add editor role later on
rules.add_perm(MeetingPermissions.CHANGE, meeting_not_archived & is_moderator)
rules.add_perm(MeetingPermissions.DELETE, meeting_not_archived & is_moderator)
rules.add_perm(
    MeetingPermissions.CHANGE_ROLES, meeting_not_archived & (is_moderator | is_manager)
)
rules.add_perm(MeetingPermissions.VIEW_ROLES, can_view_meeting | is_manager)


rules.add_perm(MeetingGroupPermissions.ADD, meeting_not_archived & is_moderator)
rules.add_perm(MeetingGroupPermissions.VIEW, can_view_meeting)
rules.add_perm(MeetingGroupPermissions.CHANGE, meeting_not_archived & is_moderator)
rules.add_perm(MeetingGroupPermissions.DELETE, meeting_not_archived & is_moderator)
