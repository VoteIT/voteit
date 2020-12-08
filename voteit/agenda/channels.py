from __future__ import annotations

from logging import getLogger

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer
from voteit.messaging.abcs import AbstractObjectChannel
from voteit.discussion.messages import (
    DiscussionPostChanged,
    DiscussionPostAdded,
    DiscussionPostDeleted,
)
from voteit.messaging.decorators import channel
from voteit.proposal.messages import (
    ProposalChanged,
    ProposalDeleted,
    ProposalAdded,
)
from voteit.proposal.models import Proposal
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer

logger = getLogger(__name__)


@channel
class AgendaItemChannel(AbstractObjectChannel):
    """ This contains generic messages for the agenda item.

        - Proposals
        - Discussions
        - Any metadata around those
    """
    name = "agenda_item"
    logger = logger
    model = AgendaItem
    permission = AgendaPermissions.VIEW


# Note: Agenda Items themselves go in the meeting channel


@receiver(post_save, sender=Proposal)
def proposal_updated(instance=None, created=None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    data = ProposalDetailSerializer(instance).data
    if created:
        msg = ProposalAdded.create(item=data)
    else:
        msg = ProposalChanged.create(item=data)
    ch.publish(msg)


@receiver(post_save, sender=DiscussionPost)
def discussion_post_change(instance=None, created=None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    data = DiscussionPostDetailSerializer(instance).data
    if created:
        msg = DiscussionPostAdded.create(item=data)
    else:
        msg = DiscussionPostChanged.create(item=data)
    ch.publish(msg)


@receiver(pre_delete, sender=Proposal)
def proposal_delete(instance=None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = ProposalDeleted.create(pk=instance.pk)
    ch.publish(msg)


@receiver(pre_delete, sender=DiscussionPost)
def discussion_post_delete(instance=None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = DiscussionPostDeleted.create(pk=instance.pk)
    ch.publish(msg)
