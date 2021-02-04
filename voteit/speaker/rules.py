from typing import Union

import rules
from django.contrib.auth.models import AbstractUser

from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerList
from voteit.speaker.roles import ROLE_LIST_MODERATOR, ROLE_SPEAKER
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.permissions import SpeakerSystemPermissions
from voteit.speaker.workflows import SpeakerListWf


@rules.predicate
def is_moderator(
    user: AbstractUser, obj: Union[SpeakerListSystem, SpeakerList]
) -> bool:
    """Check if a user has list moderator status within this speaker list system."""
    if isinstance(obj, SpeakerListSystem):
        return obj.has_roles(user, ROLE_LIST_MODERATOR)
    elif isinstance(obj, SpeakerList):
        return obj.list_system.has_roles(user, ROLE_LIST_MODERATOR)
    else:  # pragma: no cover
        return False


@rules.predicate
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

@rules.predicate
def can_view_related_meeting(
    user: AbstractUser, obj: Union[SpeakerListSystem, SpeakerList]
) -> bool:
    meeting = None
    if isinstance(obj, SpeakerListSystem):
        meeting = obj.meeting
    elif isinstance(obj, SpeakerList):
        meeting = obj.list_system.meeting
    if meeting is None:
        return False
    return user.has_perm(MeetingPermissions.VIEW, meeting)


@rules.predicate
def is_list_open(user: AbstractUser, speaker_list: SpeakerList) -> bool:
    return (
        isinstance(speaker_list, SpeakerList)
        and speaker_list.state == SpeakerListWf.OPEN
    )


@rules.predicate
def is_active_list(user: AbstractUser, speaker_list: SpeakerList) -> bool:
    return isinstance(speaker_list, SpeakerList) and speaker_list.is_active_list


@rules.predicate
def not_currently_speaking(user: AbstractUser, speaker_list: SpeakerList) -> bool:
    if isinstance(speaker_list, SpeakerList):
        if speaker_list.current is None:
            return True
        return speaker_list.current.user != user
    else:  # pragma: no cover
        return False


rules.add_perm(SpeakerListPermissions.ADD, is_moderator)  # checked against system
rules.add_perm(SpeakerListPermissions.CHANGE, is_moderator)
rules.add_perm(SpeakerListPermissions.DELETE, is_moderator)
# FIXME: Contextless systems?
rules.add_perm(
    SpeakerListPermissions.VIEW,
    can_view_related_meeting | has_speaker_role | is_moderator,
)
rules.add_perm(
    SpeakerListPermissions.ENTER, (has_speaker_role & is_list_open) | is_moderator
)
rules.add_perm(
    SpeakerListPermissions.LEAVE,
    (has_speaker_role | is_moderator) & not_currently_speaking,
)
rules.add_perm(SpeakerListPermissions.START, is_active_list & is_moderator)
rules.add_perm(SpeakerListPermissions.STOP, is_active_list & is_moderator)


@rules.predicate
def can_add_system(user: AbstractUser, context: Meeting) -> bool:
    if isinstance(context, Meeting):
        # FIXME might be a good idea to add other guards too
        return user.has_perm(MeetingPermissions.CHANGE, context)
    # FIXME: Add permission for other contexts!
    return False


rules.add_perm(SpeakerSystemPermissions.ADD, can_add_system)  # Checked against meeting
rules.add_perm(SpeakerSystemPermissions.CHANGE, is_moderator)
rules.add_perm(SpeakerSystemPermissions.DELETE, is_moderator)
rules.add_perm(
    SpeakerSystemPermissions.VIEW,
    can_view_related_meeting | has_speaker_role | is_moderator,
)
