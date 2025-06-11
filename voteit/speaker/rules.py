from __future__ import annotations
from typing import TYPE_CHECKING

import rules

from voteit.core.decorators import predicate
from voteit.core.rules import is_user
from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_upcoming_ongoing
from voteit.speaker.abcs import SpeakerSystemContext
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.permissions import SpeakerPermissions
from voteit.speaker.permissions import SpeakerSystemPermissions
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER
from voteit.speaker.workflows import SpeakerListWf

if TYPE_CHECKING:
    from voteit.core.models import User


@predicate
def is_speaker_moderator(user: User, context: SpeakerSystemContext) -> bool:
    """
    Check if a user has list moderator status within this speaker list system.
    """
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system.has_roles(user, ROLE_LIST_MODERATOR)
    raise TypeError(f"{context} is not an instance of SpeakerSystemContext")


@predicate
def has_speaker_role(user: User, context: SpeakerSystemContext) -> bool:
    """
    Check if a user has any relevant role that should allow them to enter the speaker list.
    """
    if isinstance(context, SpeakerSystemContext):
        # More likely query first
        if context.speaker_system.meeting_roles_to_speaker:
            if context.speaker_system.meeting.has_any_roles(
                user, *context.speaker_system.meeting_roles_to_speaker
            ):
                return True
        return context.speaker_system.has_any_roles(
            user, ROLE_SPEAKER, ROLE_LIST_MODERATOR
        )
    raise TypeError(f"{context} is not an instance of SpeakerSystemContext")


@predicate
def is_list_open(user: User, speaker_list: SpeakerList) -> bool:
    if isinstance(speaker_list, SpeakerList):
        return speaker_list.state == SpeakerListWf.OPEN
    raise TypeError(f"{speaker_list} is not an instance of SpeakerList")


@predicate
def is_active_list(user: User, instance: SpeakerList | Speaker) -> bool:
    if isinstance(instance, SpeakerList):
        return instance.is_active_list
    elif isinstance(instance, Speaker):
        return instance.speaker_list.is_active_list
    raise TypeError(f"{instance} is not an instance of SpeakerList | Speaker")


@predicate
def is_system_active(user: User, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system.is_active
    raise TypeError(f"{context} is not an instance of SpeakerSystemContext")


@predicate
def is_system_not_archived(user: User, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return not context.speaker_system.is_archived
    # FIXME: This sometimes receives context as None?
    # raise TypeError(f"{context} is not an instance of SpeakerSystemContext")
    return False


@predicate
def has_no_active_list(user: User, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system.active_list_id is None
    raise TypeError(f"{context} is not a speaker_system context")


@predicate
def not_currently_speaking(user: User, speaker_list: SpeakerList) -> bool:
    if isinstance(speaker_list, SpeakerList):
        if speaker := speaker_list.active_speaker():
            return speaker.user_id != user.id
        return True
    raise TypeError(f"{speaker_list} is not an instance of SpeakerList")


@predicate
def has_active_speaker_in_same_list(user: User, speaker: Speaker):
    if isinstance(speaker, Speaker):
        return Speaker.objects.filter(
            seconds__isnull=True,
            started__isnull=False,
            speaker_list_id=speaker.speaker_list_id,
        ).exists()
    raise TypeError(f"{speaker} is not a Speaker instance")


# Speaker list permissions
rules.add_perm(
    SpeakerListPermissions.ADD,
    meeting_upcoming_ongoing & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerListPermissions.CHANGE,
    meeting_upcoming_ongoing & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerListPermissions.DELETE,
    is_system_not_archived & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerListPermissions.VIEW,
    # Due to possible contextless systems later on
    can_view_meeting | is_speaker_moderator | has_speaker_role,
)
rules.add_perm(
    SpeakerListPermissions.SHUFFLE,
    meeting_upcoming_ongoing & (is_speaker_moderator | is_moderator),
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


# Speaker objects themselves
# Note: Some checks moved to serializer rather than as a permission check
rules.add_perm(
    SpeakerPermissions.ADD,
    (is_speaker_moderator | is_moderator) & meeting_upcoming_ongoing & is_system_active,
)
rules.add_perm(
    SpeakerPermissions.ENTER,
    is_list_open
    & not_currently_speaking
    & meeting_upcoming_ongoing
    & (has_speaker_role | is_moderator),
)
rules.add_perm(
    SpeakerPermissions.LEAVE,
    is_user,
)
rules.add_perm(
    SpeakerPermissions.CHANGE,
    (is_speaker_moderator | is_moderator) & is_system_not_archived,
)
rules.add_perm(
    SpeakerPermissions.DELETE,
    (is_speaker_moderator | is_moderator) & is_system_not_archived,
)
rules.add_perm(
    SpeakerPermissions.VIEW,
    is_speaker_moderator | is_moderator,
)
# We won't check validation stuff here, just permissions
rules.add_perm(
    SpeakerPermissions.START,
    (is_speaker_moderator | is_moderator)
    & is_active_list
    & ~has_active_speaker_in_same_list,
)
rules.add_perm(SpeakerPermissions.STOP, is_speaker_moderator | is_moderator)
rules.add_perm(SpeakerPermissions.UNDO, is_speaker_moderator | is_moderator)
