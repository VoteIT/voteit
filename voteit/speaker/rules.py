from __future__ import annotations
from typing import TYPE_CHECKING

import rules

from voteit.core import PERM
from voteit.core.decorators import predicate
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_participant
from voteit.meeting.rules import meeting_upcoming_ongoing
from voteit.speaker import PERM_ENTER
from voteit.speaker import PERM_SHUFFLE
from voteit.speaker import PERM_START
from voteit.speaker.abcs import SpeakerSystemContext
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
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
        return context.speaker_system and context.speaker_system.has_roles(
            user, ROLE_LIST_MODERATOR
        )
    raise TypeError(
        f"{context} is not an instance of SpeakerSystemContext"
    )  # pragma: no coverage


@predicate
def has_speaker_role(user: User, context: SpeakerSystemContext) -> bool:
    """
    Check if a user has any relevant role that should allow them to enter the speaker list.
    """
    if isinstance(context, SpeakerSystemContext):
        # More likely query first
        if context.speaker_system is None:  # pragma: no cover
            return False
        if context.speaker_system.meeting_roles_to_speaker:
            if context.speaker_system.meeting.has_any_roles(
                user, *context.speaker_system.meeting_roles_to_speaker
            ):
                return True
        return context.speaker_system.has_any_roles(
            user, ROLE_SPEAKER, ROLE_LIST_MODERATOR
        )
    raise TypeError(
        f"{context} is not an instance of SpeakerSystemContext"
    )  # pragma: no coverage


@predicate
def is_list_open(user: User, speaker_list: SpeakerList) -> bool:
    if isinstance(speaker_list, SpeakerList):
        return speaker_list.state == SpeakerListWf.OPEN
    raise TypeError(
        f"{speaker_list} is not an instance of SpeakerList"
    )  # pragma: no coverage


@predicate
def is_active_list(user: User, instance: SpeakerList | Speaker) -> bool:
    if isinstance(instance, SpeakerList):
        return instance.is_active_list
    elif isinstance(instance, Speaker):
        return instance.speaker_list.is_active_list
    raise TypeError(
        f"{instance} is not an instance of SpeakerList | Speaker"
    )  # pragma: no coverage


@predicate
def is_system_active(user: User, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system and context.speaker_system.is_active
    raise TypeError(
        f"{context} is not an instance of SpeakerSystemContext"
    )  # pragma: no coverage


@predicate
def is_system_not_archived(user: User, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system and not context.speaker_system.is_archived
    raise TypeError(
        f"{context} is not an instance of SpeakerSystemContext"
    )  # pragma: no coverage


@predicate
def has_no_active_list(user: User, context: SpeakerSystemContext) -> bool:
    if isinstance(context, SpeakerSystemContext):
        return context.speaker_system and context.speaker_system.active_list_id is None
    raise TypeError(f"{context} is not a speaker_system context")  # pragma: no coverage


@predicate
def not_currently_speaking(user: User, speaker_list: SpeakerList) -> bool:
    if isinstance(speaker_list, SpeakerList):
        if speaker := speaker_list.active_speaker():
            return speaker.user_id != user.id
        return True
    raise TypeError(
        f"{speaker_list} is not an instance of SpeakerList"
    )  # pragma: no coverage


# Speaker list permissions
rules.add_perm(
    SpeakerList.get_perm(PERM.ADD),  # Checked in serializer, not via perm
    meeting_upcoming_ongoing & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerList.get_perm(PERM.CHANGE),
    meeting_upcoming_ongoing & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerList.get_perm(PERM.DELETE),
    is_system_not_archived & (is_speaker_moderator | is_moderator),
)
rules.add_perm(
    SpeakerList.get_perm(PERM_ENTER),
    is_list_open
    & meeting_upcoming_ongoing
    & not_currently_speaking
    & (has_speaker_role | is_moderator),
)
rules.add_perm(
    SpeakerList.get_perm(PERM_SHUFFLE),
    meeting_upcoming_ongoing & (is_speaker_moderator | is_moderator),
)


# Speaker system permissions
rules.add_perm(
    SpeakerListSystem.get_perm(PERM.ADD), is_moderator & meeting_upcoming_ongoing
)  # Checked against meeting
rules.add_perm(
    SpeakerListSystem.get_perm(PERM.CHANGE),
    is_moderator & is_system_not_archived,
)
rules.add_perm(
    SpeakerListSystem.get_perm(PERM.DELETE),
    is_moderator
    & meeting_upcoming_ongoing
    & is_system_not_archived
    & has_no_active_list,
)
rules.add_perm(
    SpeakerListSystem.get_perm(PERM.CHANGE_ROLES),
    is_moderator & is_system_not_archived,
)
# This is related to roles.get message
rules.add_perm(
    SpeakerListSystem.get_perm(PERM.VIEW_ROLES),
    is_participant,
)


# Speaker objects themselves
# Note: Some checks moved to serializer rather than as a permission check
rules.add_perm(
    Speaker.get_perm(PERM.ADD),
    (is_speaker_moderator | is_moderator) & meeting_upcoming_ongoing & is_system_active,
)
# The is_speaker_moderator | is_moderator check is done on the queryset
rules.add_perm(
    Speaker.get_perm(PERM.CHANGE),
    is_system_not_archived,
)
rules.add_perm(
    Speaker.get_perm(PERM.DELETE),
    is_system_not_archived,
)
# We won't check validation stuff here, just permissions
rules.add_perm(
    Speaker.get_perm(PERM_START),
    is_active_list,
)
