from __future__ import annotations

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.proposal.messages import (
    ProposalAdded,
    ProposalChanged,
    ProposalDeleted,
)
from voteit.proposal.models import Proposal
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer


@receiver(channel_subscribed, sender=AgendaItemChannel)
def _channel_subscribed(context: AgendaItem, app_state: AppState, **kw):
    """ Populate app_state with current proposals """
    app_state.append_from_queryset(
        context.get_proposals(), ProposalDetailSerializer, ProposalAdded
    )


@receiver(post_save, sender=Proposal)
def proposal_updated(instance=None, created=None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    data = ProposalDetailSerializer(instance).data
    if created:
        msg = ProposalAdded({}, **data)
    else:
        msg = ProposalChanged({}, **data)
    ch.publish(msg)


@receiver(pre_delete, sender=Proposal)
def proposal_delete(instance=None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = ProposalDeleted({}, pk=instance.pk)
    ch.publish(msg)
