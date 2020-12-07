from __future__ import annotations
from typing import TYPE_CHECKING

import rules
from django.contrib.auth.models import AbstractUser
from voteit.core.decorators import predicate

from voteit.core.rules import is_not_archived
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.organisation.rules import is_manager
from voteit.organisation.rules import is_meeting_creator

if TYPE_CHECKING:
    pass


@predicate(role=ROLE_PARTICIPANT)
def is_participant(user: AbstractUser, meeting: Meeting) -> bool:
    """ Is this a meeting participant? """
    return isinstance(meeting, Meeting) and meeting.has_roles(user, ROLE_PARTICIPANT)


@predicate(role=ROLE_POTENTIAL_VOTER)
def is_potential_voter(user: AbstractUser, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.has_roles(
        user, ROLE_POTENTIAL_VOTER
    )


@predicate(role=ROLE_MODERATOR)
def is_moderator(user: AbstractUser, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.has_roles(user, ROLE_MODERATOR)


@predicate(role=ROLE_DISCUSSER)
def is_discusser(user: AbstractUser, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.has_roles(user, ROLE_DISCUSSER)


@predicate(role=ROLE_PROPOSER)
def is_proposer(user: AbstractUser, meeting: Meeting) -> bool:
    return isinstance(meeting, Meeting) and meeting.has_roles(user, ROLE_PROPOSER)


@predicate
def is_public(user: AbstractUser, meeting: Meeting) -> bool:
    """ The meeting is visible for everyone. """
    return isinstance(meeting, Meeting) and meeting.public


rules.add_perm(MeetingPermissions.ADD, is_manager | is_meeting_creator)
rules.add_perm(MeetingPermissions.VIEW, is_public | is_participant | is_moderator)
rules.add_perm(MeetingPermissions.MODERATE, is_not_archived & is_moderator)
# We might want to add editor role later on
rules.add_perm(MeetingPermissions.CHANGE, is_not_archived & is_moderator)
rules.add_perm(MeetingPermissions.DELETE, is_not_archived & is_moderator)
