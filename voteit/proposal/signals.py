from __future__ import annotations


from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.signals import after_sm_transition
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import receiver_all_subclasses
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.proposal.messages import ProposalChanged
from voteit.proposal.messages import ProposalDeleted
from voteit.proposal.messages import TextDocumentChanged
from voteit.proposal.messages import TextDocumentDeleted
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.rest_api.serializers import GenericProposalSerializer
from voteit.proposal.rest_api.serializers import TextDocumentSerializer


@receiver_all_subclasses(post_save, sender=Proposal)
@disable_on_raw_save
def proposal_updated(instance: Proposal = None, **kw):
    if not instance.agenda_item_id:
        return
    meeting_pk = instance.agenda_item.meeting_id
    if not meeting_pk:
        return
    moderators_ch = ModeratorsChannel(meeting_pk)
    data = GenericProposalSerializer(instance).data
    # Inject meeting attr
    data["m"] = meeting_pk
    msg = ProposalChanged(payload=data)
    moderators_ch.sync_publish(msg)
    if instance.agenda_item_id and not instance.agenda_item.is_private:
        participants_ch = ParticipantsChannel(meeting_pk)
        participants_ch.sync_publish(msg)


@receiver_all_subclasses(pre_delete, sender=Proposal)
def proposal_delete(instance: Proposal = None, **kw):
    if not instance.agenda_item_id:
        return
    meeting_pk = instance.agenda_item.meeting_id
    if not meeting_pk:
        return
    moderators_ch = ModeratorsChannel(meeting_pk)
    msg = ProposalDeleted(payload={"pk": instance.pk})
    moderators_ch.sync_publish(msg)
    if not instance.agenda_item.is_private:
        participants_ch = ParticipantsChannel(meeting_pk)
        participants_ch.sync_publish(msg)


@receiver(after_sm_transition, sender=AgendaItem)
def private_ai_published(instance: AgendaItem, source, target, event, **kw):
    """
    Notify participants of any existing proposals
    Note that proposals may appear before the agenda item does!
    """
    if (
        source.value == AgendaItemStateMachine.private.value
        and instance.meeting_id is not None
    ):
        meeting_pk = instance.meeting_id
        participants_ch = ParticipantsChannel(meeting_pk)
        # select_subclasses() is required so DiffProposals are returned as DiffProposal
        # instances and serialized with the correct serializer (includes body_diff_brief).
        proposals = (
            Proposal.objects.filter(agenda_item=instance)
            .select_subclasses()
            .prefetch_related("mentions")
        )
        for proposal in proposals:
            data = GenericProposalSerializer(proposal).data
            data["m"] = meeting_pk
            msg = ProposalChanged(payload=data)
            participants_ch.sync_publish(msg)


@receiver(post_save, sender=TextDocument)
# @disable_on_raw_save FIXME?
def text_document_updated(instance: TextDocument = None, **kw):
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
    ch.sync_publish(TextDocumentChanged(payload=data))


@receiver(pre_delete, sender=TextDocument)
def text_paragraph_delete(instance: TextDocument = None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = TextDocumentDeleted(payload={"pk": instance.pk})
    ch.sync_publish(msg)
