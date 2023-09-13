from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django_fsm import post_transition
from envelope.messages.common import Batch
from envelope.signals import channel_subscribed
from envelope.utils import AppState

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import receiver_all_subclasses
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.proposal.messages import ProposalAdded
from voteit.proposal.messages import ProposalChanged
from voteit.proposal.messages import ProposalDeleted
from voteit.proposal.messages import TextDocumentAdded
from voteit.proposal.messages import TextDocumentChanged
from voteit.proposal.messages import TextDocumentDeleted
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.rest_api.serializers import GenericProposalSerializer
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer
from voteit.proposal.rest_api.serializers import DiffProposalDetailSerializer
from voteit.proposal.rest_api.serializers import TextDocumentSerializer

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


def attach_proposals(meeting: Meeting, app_state: AppState, include_private=False):
    # Proposals
    qs = Proposal.objects.filter(
        agenda_item__meeting=meeting, diffproposal__isnull=True
    ).prefetch_related(
        "mentions",
    )
    if not include_private:
        qs = qs.exclude(agenda_item__state=AgendaItemWf.PRIVATE)
    batch = Batch(t=ProposalAdded.name, payloads=[])
    serializer = ProposalDetailSerializer(qs, many=True)
    for item in serializer.data:
        # Inject meeting attr
        item["m"] = meeting.pk
        batch.append(ProposalAdded(data=item))
    qs = DiffProposal.objects.filter(agenda_item__meeting=meeting).prefetch_related(
        "mentions", "paragraph"
    )
    if not include_private:
        qs = qs.exclude(agenda_item__state=AgendaItemWf.PRIVATE)
    serializer = DiffProposalDetailSerializer(qs, many=True)
    for item in serializer.data:
        # Inject meeting attr
        item["m"] = meeting.pk
        batch.append(ProposalAdded(data=item))
    app_state.append(batch)


@receiver(channel_subscribed, sender=ParticipantsChannel)
def participants_channel_subscribed(context: Meeting, app_state: AppState, **kw):
    """
    Populate app_state with current proposals
    """
    attach_proposals(context, app_state, include_private=False)


@receiver(channel_subscribed, sender=ModeratorsChannel)
def moderators_channel_subscribed(context: Meeting, app_state: AppState, **kw):
    """
    Populate app_state with current proposals
    """
    attach_proposals(context, app_state, include_private=True)


@receiver_all_subclasses(post_save, sender=Proposal)
@disable_on_raw_save
def proposal_updated(instance: Proposal = None, created=None, **kw):
    if not instance.agenda_item_id:
        return
    if meeting_pk := instance.agenda_item.meeting_id is None:
        return
    moderators_ch = ModeratorsChannel(meeting_pk)
    data = GenericProposalSerializer(instance).data
    # Inject meeting attr
    data["m"] = meeting_pk
    if created:
        msg = ProposalAdded(data=data)
    else:
        msg = ProposalChanged(data=data)
    moderators_ch.sync_publish(msg)
    if instance.agenda_item_id and not instance.agenda_item.is_private:
        participants_ch = ParticipantsChannel(meeting_pk)
        participants_ch.sync_publish(msg)


@receiver_all_subclasses(pre_delete, sender=Proposal)
def proposal_delete(instance: Proposal = None, **kw):
    if not instance.agenda_item_id:
        return
    if meeting_pk := instance.agenda_item.meeting_id is None:
        return
    moderators_ch = ModeratorsChannel(meeting_pk)
    msg = ProposalDeleted(pk=instance.pk)
    moderators_ch.sync_publish(msg)
    if not instance.agenda_item.is_private:
        participants_ch = ParticipantsChannel(meeting_pk)
        participants_ch.sync_publish(msg)


@receiver(post_transition, sender=AgendaItem)
def private_ai_published(instance: AgendaItem, source: str, **kw):
    """
    Notify participants of any existing proposals
    Note that proposals may appear before the agenda item does!
    """
    if source == AgendaItemWf.PRIVATE and instance.meeting_id is not None:
        meeting_pk = instance.meeting_id
        participants_ch = ParticipantsChannel(meeting_pk)
        for proposal in instance.proposals.all():
            data = GenericProposalSerializer(proposal).data
            # Inject meeting pk
            data["m"] = meeting_pk
            msg = ProposalAdded(data=data)
            participants_ch.sync_publish(msg)


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
# @disable_on_raw_save FIXME?
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
        msg = TextDocumentAdded(data=data)
    else:
        msg = TextDocumentChanged(data=data)
    ch.sync_publish(msg)


@receiver(pre_delete, sender=TextDocument)
def text_paragraph_delete(instance: TextDocument = None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = TextDocumentDeleted(pk=instance.pk)
    ch.sync_publish(msg)
