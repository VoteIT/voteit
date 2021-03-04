from typing import Union

import rules
from django.contrib.auth.models import AbstractUser

from voteit.core.decorators import predicate
from voteit.meeting.rules import (
    can_view_meeting,
    is_moderator,
    meeting_upcoming_ongoing,
)
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerList
from voteit.speaker.roles import ROLE_LIST_MODERATOR, ROLE_SPEAKER
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.permissions import SpeakerSystemPermissions
from voteit.speaker.workflows import SpeakerListWf


@predicate
def is_speaker_moderator(
    user: AbstractUser, obj: Union[SpeakerListSystem, SpeakerList]
) -> bool:
    """Check if a user has list moderator status within this speaker list system."""
    if isinstance(obj, SpeakerListSystem):
        return obj.has_roles(user, ROLE_LIST_MODERATOR)
    elif isinstance(obj, SpeakerList):
        return obj.list_system.has_roles(user, ROLE_LIST_MODERATOR)
    else:  # pragma: no cover
        return False


@predicate
def has_speaker_role(
    user: AbstractUser, obj: Union[SpeakerListSystem, SpeakerList]
) -> bool:
    """Check if a user has speaker role status within this speaker list system."""
    if isinstance(obj, SpeakerListSystem):
        return obj.has_roles(user, ROLE_SPEAKER)
    elif isinstance(obj, SpeakerList):
        return obj.list_system.has_roles(user, ROLE_SPEAKER)
    else:  # pragma: no cover
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
def is_system_active(
    user: AbstractUser, instance: Union[SpeakerListSystem, SpeakerList]
) -> bool:
    if isinstance(instance, SpeakerListSystem):
        return instance.is_active
    elif isinstance(instance, SpeakerList):
        return instance.list_system.is_active
    return False


@predicate
def is_system_not_archived(
    user: AbstractUser, instance: Union[SpeakerListSystem, SpeakerList]
) -> bool:
    if isinstance(instance, SpeakerListSystem):
        return not instance.is_archived
    elif isinstance(instance, SpeakerList):
        return not instance.list_system.is_archived
    return False


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
    SpeakerListPermissions.ADD, is_speaker_moderator & is_system_not_archived
)
rules.add_perm(
    SpeakerListPermissions.CHANGE, is_speaker_moderator & is_system_not_archived
)
rules.add_perm(
    SpeakerListPermissions.DELETE, is_speaker_moderator & is_system_not_archived
)
# FIXME: Contextless systems?
rules.add_perm(
    SpeakerListPermissions.VIEW,
    can_view_meeting | has_speaker_role | is_speaker_moderator,
)
rules.add_perm(
    SpeakerListPermissions.ENTER,
    (
        (has_speaker_role & is_list_open & is_system_active)
        | (is_speaker_moderator & is_system_not_archived)
    ),
)
# Lists should be emtied on archive, so don't bother about that
rules.add_perm(
    SpeakerListPermissions.LEAVE,
    (has_speaker_role | is_speaker_moderator) & not_currently_speaking,
)
rules.add_perm(
    SpeakerListPermissions.START,
    is_active_list & is_speaker_moderator & is_system_active,
)
rules.add_perm(SpeakerListPermissions.STOP, is_active_list & is_speaker_moderator)

# Speaker system permissions
rules.add_perm(
    SpeakerSystemPermissions.ADD, is_moderator & meeting_upcoming_ongoing
)  # Checked against meeting
rules.add_perm(
    SpeakerSystemPermissions.CHANGE,
    is_speaker_moderator & meeting_upcoming_ongoing & is_system_not_archived,
)
rules.add_perm(
    SpeakerSystemPermissions.DELETE,
    is_speaker_moderator & meeting_upcoming_ongoing & is_system_not_archived,
)
rules.add_perm(
    SpeakerSystemPermissions.VIEW,
    can_view_meeting | has_speaker_role | is_speaker_moderator,
)
