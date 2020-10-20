from __future__ import annotations
from typing import TYPE_CHECKING

import rules
from django.contrib.auth.models import AbstractUser

from voteit.core.rules import is_not_archived
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation


@rules.predicate
def is_participant(user: AbstractUser, meeting: Meeting) -> bool:
    return (
        isinstance(meeting, Meeting)
        and meeting.participants.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_potential_voter(user: AbstractUser, meeting: Meeting) -> bool:
    return (
        isinstance(meeting, Meeting)
        and meeting.potential_voters.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_moderator(user: AbstractUser, meeting: Meeting) -> bool:
    return (
        isinstance(meeting, Meeting) and meeting.moderators.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_discusser(user: AbstractUser, meeting: Meeting) -> bool:
    return (
        isinstance(meeting, Meeting) and meeting.discussers.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_proposer(user: AbstractUser, meeting: Meeting) -> bool:
    return (
        isinstance(meeting, Meeting) and meeting.proposers.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_public(user: AbstractUser, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.public


# Object permissions
@rules.predicate
def can_add_meeting(user: AbstractUser, organisation: Organisation):
    """ Meetings are added from organisations, so the check is against an organisation. """
    from voteit.organisation.rules import is_manager
    from voteit.organisation.rules import is_meeting_creator

    if organisation is not None:
        return is_manager(user, organisation) or is_meeting_creator(user, organisation)


rules.add_perm(MeetingPermissions.ADD, can_add_meeting)
rules.add_perm(MeetingPermissions.VIEW, is_public | is_participant | is_moderator)
rules.add_perm(MeetingPermissions.MODERATE, is_not_archived & is_moderator)
# We might want to add editor role later on
rules.add_perm(MeetingPermissions.CHANGE, is_not_archived & is_moderator)
rules.add_perm(MeetingPermissions.DELETE, is_not_archived & is_moderator)
