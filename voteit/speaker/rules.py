from __future__ import annotations
from typing import TYPE_CHECKING

import rules

from voteit.core.decorators import predicate
from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_upcoming_ongoing
from voteit.speaker.abcs import SpeakerSystemContext
from voteit.speaker.models import SpeakerList
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.permissions import SpeakerPermissions
from voteit.speaker.permissions import SpeakerSystemPermissions
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER
from voteit.speaker.workflows import SpeakerListWf

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


@predicate
def is_speaker_moderator(user: AbstractUser, context: SpeakerSystemContext) -> bool:
    """
    Check if a user has list moderator status within this speaker list system.
    """
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system.has_roles(user, ROLE_LIST_MODERATOR)
    # pragma: no cover
    return False


@predicate
def has_speaker_role(user: AbstractUser, context: SpeakerSystemContext) -> bool:
    """
    Check if a user has speaker role status within this speaker list system.
    """
    if isinstance(context, SpeakerSystemContext):
        if context.speaker_system.has_roles(user, ROLE_SPEAKER):
            return True
        if context.speaker_system.meeting_roles_to_speaker:
            return context.speaker_system.meeting.has_any_roles(
                user, *context.speaker_system.meeting_roles_to_speaker
            )
    return False


@predicate
def is_list_open(user: AbstractUser, speaker_list: SpeakerList) -> bool:
    return (
        isinstance(speaker_list, SpeakerList)
        and speaker_list.state == SpeakerListWf.OPEN
    )


@predicate
def is_active_list(user: AbstractUser, speaker_list: SpeakerList) -> bool:
    return isinstance(speaker_list, SpeakerList) and speaker_list.is_active_list


@predicate
def is_system_active(user: AbstractUser, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system.is_active
    return False


@predicate
def is_system_not_archived(user: AbstractUser, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return not context.speaker_system.is_archived
    return False


@predicate
def has_no_active_list(user: AbstractUser, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system.active_list_id is None
    raise TypeError(f"{context} is not a speaker_system context")


@predicate
def not_currently_speaking(user: AbstractUser, speaker_list: SpeakerList) -> bool:
    if isinstance(speaker_list, SpeakerList):
        if speaker_list.current is None:
            return True
        return speaker_list.current.user != user
    else:  # pragma: no cover
        return False


# Speaker list permissions
rules.add_perm(
    SpeakerListPermissions.ADD,
    is_system_not_archived & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerListPermissions.CHANGE,
    is_system_not_archived & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerListPermissions.DELETE,
    is_system_not_archived & (is_speaker_moderator | is_moderator),
)

# FIXME: Contextless systems?
rules.add_perm(
    SpeakerListPermissions.VIEW,
    # Due to possible contextless systems later on
    can_view_meeting | is_speaker_moderator | has_speaker_role,
)
rules.add_perm(
    SpeakerListPermissions.ENTER,
    not_currently_speaking & (has_speaker_role & is_list_open & is_system_active)
    | (is_system_not_archived & (is_speaker_moderator | is_moderator)),
)

# Lists should be emptied on archive, so don't bother about that
rules.add_perm(
    SpeakerListPermissions.LEAVE,
    not_currently_speaking,
)
rules.add_perm(
    SpeakerListPermissions.START,
    is_active_list & is_system_active & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerListPermissions.STOP, is_active_list & (is_speaker_moderator | is_moderator)
)

# Speaker system permissions
rules.add_perm(
    SpeakerSystemPermissions.ADD, is_moderator & meeting_upcoming_ongoing
)  # Checked against meeting
rules.add_perm(
    SpeakerSystemPermissions.CHANGE,
    is_moderator & meeting_upcoming_ongoing & is_system_not_archived,
)
rules.add_perm(
    SpeakerSystemPermissions.MANAGE,
    is_moderator | is_speaker_moderator,
)
rules.add_perm(
    SpeakerSystemPermissions.DELETE,
    is_moderator
    & meeting_upcoming_ongoing
    & is_system_not_archived
    & has_no_active_list,
)
rules.add_perm(
    SpeakerSystemPermissions.VIEW,
    # Due to possible contextless systems later on
    can_view_meeting | is_speaker_moderator | has_speaker_role,
)
rules.add_perm(
    SpeakerSystemPermissions.CHANGE_ROLES,
    is_moderator & meeting_upcoming_ongoing & is_system_not_archived,
)
rules.add_perm(
    SpeakerSystemPermissions.VIEW_ROLES,
    # Due to possible contextless systems later on
    can_view_meeting | is_speaker_moderator | has_speaker_role,
)


# Speaker objects themselves, only for list moderators really
rules.add_perm(
    SpeakerPermissions.ADD,
    (is_speaker_moderator | is_moderator) & meeting_upcoming_ongoing,
)
rules.add_perm(
    SpeakerPermissions.CHANGE,
    (is_speaker_moderator | is_moderator)
    & meeting_upcoming_ongoing
    & is_system_not_archived,
)
rules.add_perm(
    SpeakerPermissions.DELETE,
    (is_speaker_moderator | is_moderator)
    & meeting_upcoming_ongoing
    & is_system_not_archived,
)
rules.add_perm(
    SpeakerPermissions.VIEW,
    is_speaker_moderator | is_moderator,
)
