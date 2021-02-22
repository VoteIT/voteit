from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.proposal.messages import (
    ProposalAdded,
    ProposalChanged,
    ProposalDeleted,
)
from voteit.proposal.models import Proposal
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer
from voteit.agenda.workflows import AgendaItemWf

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


@receiver(channel_subscribed, sender=ParticipantsChannel)
def participants_channel_subscribed(context: Meeting, app_state: AppState, **kw):
    """ Populate app_state with current proposals """
    app_state.append_from_queryset(
        Proposal.objects.filter(agenda_item__meeting=context).exclude(
            agenda_item__state=AgendaItemWf.PRIVATE
        ),
        ProposalDetailSerializer,
        ProposalAdded,
    )


@receiver(channel_subscribed, sender=ModeratorsChannel)
def moderators_channel_subscribed(context: Meeting, app_state: AppState, **kw):
    """ Populate app_state with current proposals """
    app_state.append_from_queryset(
        Proposal.objects.filter(agenda_item__meeting=context),
        ProposalDetailSerializer,
        ProposalAdded,
    )


@receiver(post_save, sender=Proposal)
def proposal_updated(instance: Proposal = None, created=None, **kw):
    if instance.meeting is None:
        return
    moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
    data = ProposalDetailSerializer(instance).data
    if created:
        msg = ProposalAdded({}, **data)
    else:
        msg = ProposalChanged({}, **data)
    moderators_ch.publish(msg)
    if instance.agenda_item and not instance.agenda_item.is_private:
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        participants_ch.publish(msg)


@receiver(pre_delete, sender=Proposal)
def proposal_delete(instance=None, **kw):
    if instance.meeting is None:
        return
    moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
    msg = ProposalDeleted({}, pk=instance.pk)
    moderators_ch.publish(msg)
    if instance.agenda_item and not instance.agenda_item.is_private:
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        participants_ch.publish(msg)
