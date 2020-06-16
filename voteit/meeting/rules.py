from __future__ import annotations
from typing import TYPE_CHECKING

import rules
from django.contrib.auth.models import User

from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.workflows import MeetingWf

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation


@rules.predicate
def is_participant(user: User, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.participants.filter(pk=user.pk).exists()


@rules.predicate
def is_potential_voter(user: User, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.potential_voters.filter(pk=user.pk).exists()


@rules.predicate
def is_moderator(user: User, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.moderators.filter(pk=user.pk).exists()


@rules.predicate
def is_discusser(user: User, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.discussers.filter(pk=user.pk).exists()


@rules.predicate
def is_proposer(user: User, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.proposers.filter(pk=user.pk).exists()


@rules.predicate
def is_not_archived(user: User, meeting: Meeting) -> bool:
    # Keep negated state here since it might be called with meeting as None!
    # Using is_archived with negation will cause a false positive for that case
    return isinstance(meeting, Meeting) and meeting.state != MeetingWf.ARCHIVED


@rules.predicate
def is_public(user: User, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.public


# Object permissions
@rules.predicate
def can_add_meeting(user: User, organisation: Organisation):
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
