import rules
from django.contrib.auth.models import AbstractUser
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions

from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import Speaker
from voteit.speaker.permissions import (
    SpeakerListPermissions,
    SpeakerPermissions,
    SpeakerSystemPermissions,
)
from voteit.speaker.workflows import SpeakerListWf

# FIXME: We might want to tweak permissions later on, so I've only added some of them /rho


@rules.predicate
def is_list_moderator(user: AbstractUser, list_system: SpeakerListSystem) -> bool:
    return (
        isinstance(list_system, SpeakerListSystem)
        and list_system.moderators.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_list_speaker(user: AbstractUser, list_system: SpeakerListSystem) -> bool:
    return (
        isinstance(list_system, SpeakerListSystem)
        and list_system.speakers.filter(pk=user.pk).exists()
    )


@rules.predicate
def can_add_speaker(user: AbstractUser, speaker_list: SpeakerList):
    """
        Add a speaker to a list if:
        1. The list is open AND you're a speaker
        2. You're list moderator
    """
    return isinstance(speaker_list, SpeakerList) and (
        (
            speaker_list.state == SpeakerListWf.OPEN
            and is_list_speaker(user, speaker_list.list_system)
        )
        or is_list_moderator(user, speaker_list.list_system)
    )


@rules.predicate
def can_change_speaker(user: AbstractUser, speaker: Speaker):
    """ Only moderators."""
    return isinstance(speaker, Speaker) and is_list_moderator(
        user, speaker.list.list_system
    )


@rules.predicate
def can_delete_speaker(user: AbstractUser, speaker: Speaker):
    """ Users may delete themselves (remove from list) if they're queued,
        but never if they're speaking or if it's an old entry.
        Moderators can always delete.
    """
    return isinstance(speaker, Speaker) and (
        (speaker.user == user and speaker.in_queue)
        or is_list_moderator(user, speaker.list.list_system)
    )


@rules.predicate
def can_view_speaker(user: AbstractUser, speaker: Speaker):
    """ View permission on attached meeting, speakers or list moderators"""
    # FIXME: This might change a lot
    if isinstance(speaker, Speaker):
        system = speaker.list.list_system
        return (
            is_list_speaker(user, system)
            or is_list_moderator(user, system)
            or user.has_perm(MeetingPermissions.VIEW, system.meeting)
        )


rules.add_perm(SpeakerPermissions.ADD, can_add_speaker)
rules.add_perm(SpeakerPermissions.CHANGE, can_change_speaker)
rules.add_perm(SpeakerPermissions.DELETE, can_delete_speaker)
rules.add_perm(SpeakerPermissions.VIEW, can_view_speaker)


@rules.predicate
def can_add_speaker_list(user: AbstractUser, list_system: SpeakerListSystem):
    return is_list_moderator(user, list_system)


@rules.predicate
def can_change_speaker_List(user: AbstractUser, speaker_list: SpeakerList):
    return isinstance(speaker_list, SpeakerList) and is_list_moderator(
        user, speaker_list.list_system
    )


@rules.predicate
def can_delete_speaker_list(user: AbstractUser, speaker_list: SpeakerList):
    return isinstance(speaker_list, SpeakerList) and is_list_moderator(
        user, speaker_list.list_system
    )


@rules.predicate
def can_view_speaker_list(user: AbstractUser, speaker_list: SpeakerList):
    """ Delegate to speaker list system VIEW
    """
    return isinstance(speaker_list, SpeakerList) and user.has_perm(
        SpeakerSystemPermissions.VIEW, speaker_list.list_system
    )


rules.add_perm(SpeakerListPermissions.ADD, can_add_speaker_list)
rules.add_perm(SpeakerListPermissions.CHANGE, can_change_speaker_List)
rules.add_perm(SpeakerListPermissions.DELETE, can_delete_speaker_list)
rules.add_perm(SpeakerListPermissions.VIEW, can_view_speaker_list)


@rules.predicate
def can_add_system(user: AbstractUser, context: Meeting):
    if isinstance(context, Meeting):
        # FIXME might be a good idea to add other guards too
        return user.has_perm(MeetingPermissions.CHANGE, context)
    # FIXME: Add permission for other contexts!


@rules.predicate
def can_change_system(user: AbstractUser, system: SpeakerListSystem):
    return is_list_moderator(user, system)


@rules.predicate
def can_delete_system(user: AbstractUser, system: SpeakerListSystem):
    return is_list_moderator(user, system)


@rules.predicate
def can_view_system(user: AbstractUser, system: SpeakerListSystem):
    if isinstance(system, SpeakerListSystem):
        return (
            is_list_speaker(user, system)
            or is_list_moderator(user, system)
            or user.has_perm(MeetingPermissions.VIEW, system.meeting)
        )


rules.add_perm(SpeakerSystemPermissions.ADD, can_add_system)
rules.add_perm(SpeakerSystemPermissions.CHANGE, can_change_system)
rules.add_perm(SpeakerSystemPermissions.DELETE, can_delete_system)
rules.add_perm(SpeakerSystemPermissions.VIEW, can_view_system)
