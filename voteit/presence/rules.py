from typing import Union

import rules
from django.contrib.auth.models import AbstractUser
from voteit.core.decorators import predicate

from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rules import (
    is_participant,
    is_moderator,
    can_view_meeting,
    meeting_upcoming_ongoing,
)
from voteit.presence.models import PresenceCheck, Presence
from voteit.presence.permissions import PresenceSystemPermissions
from voteit.presence.permissions import PresencePermissions
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.workflows import PresenceCheckWf


rules.add_perm(PresenceSystemPermissions.ADD, meeting_upcoming_ongoing & is_moderator)
rules.add_perm(
    PresenceSystemPermissions.CHANGE, meeting_upcoming_ongoing & is_moderator
)
rules.add_perm(
    PresenceSystemPermissions.DELETE, meeting_upcoming_ongoing & is_moderator
)
rules.add_perm(PresenceSystemPermissions.VIEW, is_participant)


@predicate
def is_check_open(user: AbstractUser, instance: Union[PresenceCheck, Presence]):
    if isinstance(instance, PresenceCheck):
        return instance.state == PresenceCheckWf.OPEN
    elif isinstance(instance, Presence):
        return instance.presence_check.state == PresenceCheckWf.OPEN
    return False


@predicate
def can_view_presence_check(user: AbstractUser, presence_check: PresenceCheck):
    """ Delegate check to meeting. """
    return isinstance(presence_check, PresenceCheck) and user.has_perm(
        MeetingPermissions.VIEW, presence_check.presence_system.meeting
    )


rules.add_perm(PresenceCheckPermissions.ADD, meeting_upcoming_ongoing & is_moderator)
rules.add_perm(PresenceCheckPermissions.CHANGE, is_check_open & is_moderator)
rules.add_perm(PresenceCheckPermissions.DELETE, meeting_upcoming_ongoing & is_moderator)
rules.add_perm(PresenceCheckPermissions.VIEW, can_view_meeting)


@predicate
def is_present_user(user: AbstractUser, presence: Presence) -> bool:
    return isinstance(presence, Presence) and user is not None and user == presence.user


rules.add_perm(PresencePermissions.ADD, is_check_open & (is_participant | is_moderator))
rules.add_perm(
    PresencePermissions.DELETE, is_check_open & (is_present_user | is_moderator)
)
# GDPR might change this behaviour
rules.add_perm(PresencePermissions.VIEW, is_present_user | is_moderator)
