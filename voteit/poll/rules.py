import rules
from django.contrib.auth.models import User

from voteit.poll.models import Poll
from voteit.poll.workflows import PollWf


@rules.predicate
def is_voter(user: User, poll: Poll):
    # FIXME: Probably some smarter way to do this.
    return poll.electoral_register and user in poll.electoral_register.voters.all()


@rules.predicate
def can_vote_now(user: User, poll: Poll):
    return poll.state == PollWf.ONGOING and is_voter(user, poll)
