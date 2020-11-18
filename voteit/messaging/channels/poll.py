from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save
from django.dispatch import receiver

from voteit.messaging.channels.abcs import AbstractObjectChannel
from voteit.messaging.messages.poll import PollStatus
from voteit.messaging.registries import channel_registry
from voteit.poll.abcs import Vote
from voteit.poll.models import Poll
from voteit.poll.permissions import PollPermissions

logger = getLogger(__name__)


@channel_registry("poll")
class PollChannel(AbstractObjectChannel):
    """ A channel for specific poll updates.

        Transport for
        - Voting

        (Poll objects themselves are part of the meeting channel)
    """

    logger = logger
    Model = Poll

    @property
    def channel_name(self) -> str:
        """ Return name of this channel based on the primary key of an object"""
        return f"poll_{self.pk}"

    def allow_subscribe(self, user):
        instance = self.get_instance()
        return user.has_perm(PollPermissions.VIEW, instance)


# FIXME: sender=Vote instead, but it's a metaclass so it requires some tinkering with signals :/ /robinharms
@receiver(post_save)
def vote_added(instance=None, created=None, **kw):
    # We don't have to count updated votes!
    if created and isinstance(instance, Vote) and instance.method is not None:
        msg = PollStatus(
            pk=instance.pk,
            voted=instance.method.vote_set.count(),
            total=instance.method.poll.electoral_register.voters.count(),
        )
        channel = PollChannel.from_instance(instance.method.poll)
        channel.sync_publish(msg)
