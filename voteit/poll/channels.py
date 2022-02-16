from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save
from django.dispatch import receiver

from voteit.core.decorators import disable_on_raw_save
from voteit.messaging.abcs import AbstractObjectChannel
from voteit.messaging.decorators import channel
from voteit.poll.messages import PollStatus
from voteit.poll.models import Vote
from voteit.poll.models import Poll
from voteit.poll.permissions import PollPermissions

logger = getLogger(__name__)


@channel
class PollChannel(AbstractObjectChannel):
    """A channel for specific poll updates.

    Transport for
    - Voting

    (Poll objects themselves are part of the meeting channel)
    """

    name = "poll"
    permission = PollPermissions.VIEW
    logger = logger
    model = Poll


# FIXME: sender=Vote instead, but it's a metaclass so it requires some tinkering with signals :/ /robinharms
@receiver(post_save)
@disable_on_raw_save
def vote_added(instance=None, created=None, **kw):
    # We don't have to count updated votes!
    if created and isinstance(instance, Vote):
        poll = instance.poll
        msg = PollStatus.create(
            pk=poll.pk,
            voted=poll.votes.count(),
            total=poll.electoral_register.voters.count(),
        )
        ch = PollChannel.from_instance(poll)
        ch.publish(msg)
