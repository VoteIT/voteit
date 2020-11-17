from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer
from voteit.messaging.channels.abcs import AbstractObjectChannel
from voteit.messaging.messages.discussion_post import DiscussionPostUpdated
from voteit.messaging.messages.proposal import ProposalUpdated, ProposalDeleted
from voteit.messaging.registries import channel_registry
from voteit.proposal.models import Proposal
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer

logger = getLogger(__name__)


@channel_registry("agenda_item")
class AgendaItemChannel(AbstractObjectChannel):
    """ This contains generic messages for the agenda item.

        - Proposals
        - Discussions
        - Any metadata around those
    """
    logger = logger
    Model = AgendaItem

    @property
    def channel_name(self) -> str:
        """ Return name of this channel based on the primary key of an object"""
        return f"ai_{self.pk}"

    def allow_subscribe(self, user):
        instance = self.get_instance()
        return user.has_perm(AgendaPermissions.VIEW, instance)


# Note: Agenda Items themselves go in the meeting channel


@receiver(post_save, sender=Proposal)
def proposal_change(instance=None, **kw):
    if instance.agenda_item is None:
        return
    channel = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = ProposalUpdated(items=[ProposalDetailSerializer(instance).data])
    channel.sync_publish(msg)


@receiver(post_save, sender=DiscussionPost)
def discussion_post_change(instance=None, **kw):
    if instance.agenda_item is None:
        return
    channel = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = DiscussionPostUpdated(items=[DiscussionPostDetailSerializer(instance).data])
    channel.sync_publish(msg)


@receiver(post_delete, sender=Proposal)
@receiver(post_delete, sender=DiscussionPost)
def proposal_delete(instance=None, **kw):
    if instance.agenda_item is None:
        return
    channel = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = ProposalDeleted(items=[instance.pk])
    channel.sync_publish(msg)
