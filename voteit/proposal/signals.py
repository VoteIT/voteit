from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django_fsm import post_transition

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.agenda.workflows import AgendaItemWf
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.proposal.messages import ProposalAdded
from voteit.proposal.messages import ProposalChanged
from voteit.proposal.messages import ProposalDeleted
from voteit.proposal.messages import TextDocumentAdded
from voteit.proposal.messages import TextDocumentChanged
from voteit.proposal.messages import TextDocumentDeleted
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.rest_api.serializers import GenericProposalSerializer
from voteit.proposal.rest_api.serializers import TextDocumentSerializer

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


@receiver(channel_subscribed, sender=ParticipantsChannel)
def participants_channel_subscribed(context: Meeting, app_state: AppState, **kw):
    """Populate app_state with current proposals"""
    app_state.append_from_queryset(
        Proposal.objects.filter(agenda_item__meeting=context)
        .exclude(agenda_item__state=AgendaItemWf.PRIVATE)
        .select_subclasses(),
        GenericProposalSerializer,
        ProposalAdded,
    )


@receiver(channel_subscribed, sender=ModeratorsChannel)
def moderators_channel_subscribed(context: Meeting, app_state: AppState, **kw):
    """Populate app_state with current proposals"""
    app_state.append_from_queryset(
        Proposal.objects.filter(agenda_item__meeting=context).select_subclasses(),
        GenericProposalSerializer,
        ProposalAdded,
    )


@receiver(post_save, sender=Proposal)
def proposal_updated(instance: Proposal = None, created=None, **kw):
    if instance.meeting is None:
        return
    moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
    data = GenericProposalSerializer(instance).data
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


@receiver(post_transition, sender=AgendaItem)
def private_ai_published(instance: AgendaItem, source: str, **kw):
    """Notify participants of any existing proposals
    Note that proposals may appear before the agenda item does!"""
    if source == AgendaItemWf.PRIVATE and instance.meeting is not None:
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        for proposal in instance.proposals.all():
            data = GenericProposalSerializer(proposal).data
            msg = ProposalAdded({}, **data)
            participants_ch.publish(msg)


@receiver(channel_subscribed, sender=AgendaItemChannel)
def agenda_item_channel_subscribed(context: AgendaItem, app_state: AppState, **kw):
    """
    Populate app_state with TextDocuments
    """
    app_state.append_from_queryset(
        TextDocument.objects.filter(agenda_item=context),
        TextDocumentSerializer,
        TextDocumentAdded,
    )


@receiver(post_save, sender=TextDocument)
def text_document_updated(instance: TextDocument = None, created=None, **kw):
    """
    Create TextParagraphs and push result.
    We need to create text paragraphs post save but we want to do it before the message is sent
    """
    if instance.should_refresh:
        instance.text_paragraphs.all().delete()
        instance.create_text_paragraphs()
    # No need to notify
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    data = TextDocumentSerializer(instance).data
    if created:
        msg = TextDocumentAdded({}, **data)
    else:
        msg = TextDocumentChanged({}, **data)
    ch.publish(msg)


@receiver(pre_delete, sender=TextDocument)
def text_paragraph_delete(instance: TextDocument = None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = TextDocumentDeleted({}, pk=instance.pk)
    ch.publish(msg)
