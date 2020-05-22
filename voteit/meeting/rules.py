import rules
from django.contrib.auth.models import User

from voteit.meeting.models import Meeting


@rules.predicate
def is_participant(user: User, meeting: Meeting):
    # FIXME: Probably some smarter way to do this.
    return user in meeting.participants.all()


@rules.predicate
def is_potential_voter(user: User, meeting: Meeting):
    return user in meeting.potential_voters.all()
