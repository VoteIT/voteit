import rules
from django.contrib.auth.models import AbstractUser

from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rules import is_participant
from voteit.presence.models import PresenceSystem, PresenceCheck, Presence
from voteit.presence.permissions import PresenceSystemPermissions
from voteit.presence.permissions import PresencePermissions
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.workflows import PresenceCheckWf


@rules.predicate
def can_add_presence_system(user: AbstractUser, meeting: Meeting):
    """ Delegate check to moderate perm on meeting. """
    return isinstance(meeting, Meeting) and user.has_perm(
        MeetingPermissions.MODERATE, meeting
    )


@rules.predicate
def can_manage_presence_system(user: AbstractUser, system: PresenceSystem):
    """ Delegate check to moderate perm on meeting. """

    return isinstance(system, PresenceSystem) and user.has_perm(
        MeetingPermissions.MODERATE, system.meeting
    )


@rules.predicate
def can_view_presence_system(user: AbstractUser, system: PresenceSystem):
    """ Delegate check to view perm on meeting. """

    return isinstance(system, PresenceSystem) and user.has_perm(
        MeetingPermissions.VIEW, system.meeting
    )


rules.add_perm(PresenceSystemPermissions.ADD, can_add_presence_system)
rules.add_perm(PresenceSystemPermissions.CHANGE, can_manage_presence_system)
rules.add_perm(PresenceSystemPermissions.DELETE, can_manage_presence_system)
rules.add_perm(PresenceSystemPermissions.VIEW, can_view_presence_system)


@rules.predicate
def can_add_presence_check(user: AbstractUser, system: PresenceSystem):
    """ Delegate check to meeting. """
    return isinstance(system, PresenceSystem) and user.has_perm(
        MeetingPermissions.MODERATE, system.meeting
    )


@rules.predicate
def is_check_ongoing(user: AbstractUser, presence_check: PresenceCheck):
    return (
        isinstance(presence_check, PresenceCheck)
        and presence_check.state == PresenceCheckWf.OPEN
    )


@rules.predicate
def can_manage_presence_check(user: AbstractUser, presence_check: PresenceCheck):
    """ Delegate check to meeting. """
    return isinstance(presence_check, PresenceCheck) and user.has_perm(
        MeetingPermissions.MODERATE, presence_check.presence_system.meeting
    )


@rules.predicate
def can_view_presence_check(user: AbstractUser, presence_check: PresenceCheck):
    """ Delegate check to meeting. """
    return isinstance(presence_check, PresenceCheck) and user.has_perm(
        MeetingPermissions.VIEW, presence_check.presence_system.meeting
    )


rules.add_perm(PresenceCheckPermissions.ADD, can_add_presence_check)
rules.add_perm(
    PresenceCheckPermissions.CHANGE, is_check_ongoing & can_manage_presence_check
)
rules.add_perm(PresenceCheckPermissions.DELETE, can_manage_presence_check)
rules.add_perm(PresenceCheckPermissions.VIEW, can_view_presence_check)


@rules.predicate
def can_add_presence(user: AbstractUser, presence_check: PresenceCheck):
    return (
        isinstance(presence_check, PresenceCheck)
        and is_check_ongoing(user, presence_check)
        and (
            is_participant(user, presence_check.presence_system.meeting)
            or can_manage_presence_check(user, presence_check)
        )
    )


@rules.predicate
def can_delete_presence(user: AbstractUser, presence: Presence):
    return (
        isinstance(presence, Presence)
        and is_check_ongoing(user, presence.presence_check)
        and (
            user == presence.user
            or can_manage_presence_check(user, presence.presence_check)
        )
    )


@rules.predicate
def can_view_presence(user: AbstractUser, presence: Presence):
    # FIXME: We don't really know about the permissions that should be used for this
    # GDPR might change this behaviour
    return (
        isinstance(presence, Presence)
        and user == presence.user
        or can_manage_presence_check(user, presence.presence_check)
    )


rules.add_perm(PresencePermissions.ADD, can_add_presence)
rules.add_perm(PresencePermissions.DELETE, can_delete_presence)
rules.add_perm(PresencePermissions.VIEW, can_view_presence)
