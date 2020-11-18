from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer
from voteit.messaging.channels.abcs import AbstractObjectChannel
from voteit.messaging.messages.discussion_post import DiscussionPostChanged, DiscussionPostAdded, DiscussionPostDeleted
from voteit.messaging.messages.proposal import ProposalChanged, ProposalDeleted, ProposalAdded
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
def proposal_updated(instance=None, created=None, **kw):
    if instance.agenda_item is None:
        return
    channel = AgendaItemChannel.from_instance(instance.agenda_item)
    data = ProposalDetailSerializer(instance).data
    if created:
        msg = ProposalAdded(item=data)
    else:
        msg = ProposalChanged(item=data)
    channel.sync_publish(msg)


@receiver(post_save, sender=DiscussionPost)
def discussion_post_change(instance=None, created=None, **kw):
    if instance.agenda_item is None:
        return
    channel = AgendaItemChannel.from_instance(instance.agenda_item)
    data = DiscussionPostDetailSerializer(instance).data
    if created:
        msg = DiscussionPostAdded(item=data)
    else:
        msg = DiscussionPostChanged(item=data)
    channel.sync_publish(msg)


@receiver(pre_delete, sender=Proposal)
def proposal_delete(instance=None, **kw):
    if instance.agenda_item is None:
        return
    channel = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = ProposalDeleted(pk=instance.pk)
    channel.sync_publish(msg)


@receiver(pre_delete, sender=DiscussionPost)
def discussion_post_delete(instance=None, **kw):
    if instance.agenda_item is None:
        return
    channel = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = DiscussionPostDeleted(pk=instance.pk)
    channel.sync_publish(msg)
