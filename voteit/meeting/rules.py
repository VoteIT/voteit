import rules
from django.contrib.auth.models import User

from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.workflows import MeetingWf


@rules.predicate
def is_participant(user: User, meeting: Meeting) -> bool:
    return meeting.participants.filter(pk=user.pk).exists()


@rules.predicate
def is_potential_voter(user: User, meeting: Meeting) -> bool:
    return meeting.potential_voters.filter(pk=user.pk).exists()


@rules.predicate
def is_moderator(user: User, meeting: Meeting) -> bool:
    return meeting.moderators.filter(pk=user.pk).exists()


@rules.predicate
def is_discusser(user: User, meeting: Meeting) -> bool:
    return meeting.discussers.filter(pk=user.pk).exists()


@rules.predicate
def is_proposer(user: User, meeting: Meeting) -> bool:
    return meeting.proposers.filter(pk=user.pk).exists()


# Object permissions
@rules.predicate
def can_view_meeting(user: User, meeting: Meeting):
    if meeting is not None:
        if meeting.public:
            return True
        return is_participant(user, meeting) or is_moderator(user, meeting)


rules.add_perm(MeetingPermissions.VIEW, can_view_meeting)


@rules.predicate
def can_moderate_meeting(user: User, meeting: Meeting):
    if meeting is not None:
        if meeting.state != MeetingWf.ARCHIVED:
            return is_moderator(user, meeting)


rules.add_perm(MeetingPermissions.MODERATE, can_moderate_meeting)
# We might want to add editor role later on
rules.add_perm(MeetingPermissions.CHANGE, can_moderate_meeting)
rules.add_perm(MeetingPermissions.DELETE, can_moderate_meeting)
