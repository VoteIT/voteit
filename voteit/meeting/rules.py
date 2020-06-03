import rules
from django.contrib.auth.models import User

from voteit.meeting.models import Meeting


@rules.predicate
def is_participant(user: User, meeting: Meeting) -> bool:
    return meeting.participants.filter(pk=user.pk).exists()


@rules.predicate
def is_potential_voter(user: User, meeting: Meeting) -> bool:
    return meeting.potential_voters.filter(pk=user.pk).exists()


@rules.predicate
def is_moderator(user: User, meeting: Meeting) -> bool:
    return meeting.moderators.filter(pk=user.pk).exists()
