from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from envelope.messages.common import Batch
from envelope.signals import channel_subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.signals import after_sm_transition
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import receiver_all_subclasses
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.proposal.diff import Changes
from voteit.proposal.messages import ProposalAdded
from voteit.proposal.messages import ProposalChanged
from voteit.proposal.messages import ProposalDeleted
from voteit.proposal.messages import TextDocumentAdded
from voteit.proposal.messages import TextDocumentChanged
from voteit.proposal.messages import TextDocumentDeleted
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.rest_api.serializers import DiffProposalDetailSerializer
from voteit.proposal.rest_api.serializers import GenericProposalSerializer
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer
from voteit.proposal.rest_api.serializers import TextDocumentSerializer

if TYPE_CHECKING:
    from envelope.channels.models import AppState

    from voteit.meeting.models import Meeting


def _fetch_mentions_map(pks: list[int]) -> dict[int, list[int]]:
    """Return {proposal_pk: [user_pk, ...]} for the given proposal PKs.

    Queries the M2M through table directly in one query rather than using
    prefetch_related, which would bypass the prefetch cache when .values_list()
    is called and cause an N+1 query per proposal.
    """
    if not pks:
        return {}
    result: dict[int, list] = {}
    for row in Proposal.mentions.through.objects.filter(proposal_id__in=pks).values(
        "proposal_id", "user_id"
    ):
        result.setdefault(row["proposal_id"], []).append(row["user_id"])
    return result


def attach_proposals(meeting: Meeting, app_state: AppState, include_private=False):
    # Proposals — exclude "mentions" from .values() because M2M in values() produces one row
    # per relationship (fan-out), causing duplicate proposals. Inject mentions separately.
    exclude_fields = {"body_diff_brief", "body_diff", "shortname", "mentions"}
    proposal_fields = set(ProposalDetailSerializer.Meta.fields) - exclude_fields
    qs = Proposal.objects.filter(
        agenda_item__meeting=meeting, diffproposal__isnull=True
    )
    if not include_private:
        qs = qs.exclude(agenda_item__state=AgendaItemStateMachine.private.value)
    batch = Batch(t=ProposalAdded.name, payloads=[])
    shortname = get_model_shortname(Proposal)
    items = list(qs.values(*proposal_fields))
    mentions_map = _fetch_mentions_map([item["pk"] for item in items])
    for item in items:
        item["m"] = meeting.pk
        item["shortname"] = shortname
        item["mentions"] = mentions_map.get(item["pk"], [])
        batch.append(ProposalAdded(data=item))

    diff_fields = (set(DiffProposalDetailSerializer.Meta.fields) - exclude_fields) | {
        "para_body"
    }
    diff_qs = DiffProposal.objects.filter(agenda_item__meeting=meeting).annotate(
        para_body=models.F("paragraph__body")
    )
    if not include_private:
        diff_qs = diff_qs.exclude(
            agenda_item__state=AgendaItemStateMachine.private.value
        )
    shortname = get_model_shortname(DiffProposal)
    diff_items = list(diff_qs.values(*diff_fields))
    diff_mentions_map = _fetch_mentions_map([item["pk"] for item in diff_items])
    for item in diff_items:
        para_body = item.pop("para_body")
        item["body_diff_brief"] = Changes(para_body, item["body"]).get_html(brief=True)
        item["shortname"] = shortname
        item["m"] = meeting.pk
        item["mentions"] = diff_mentions_map.get(item["pk"], [])
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
    meeting_pk = instance.agenda_item.meeting_id
    if not meeting_pk:
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
    meeting_pk = instance.agenda_item.meeting_id
    if not meeting_pk:
        return
    moderators_ch = ModeratorsChannel(meeting_pk)
    msg = ProposalDeleted(pk=instance.pk)
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
            msg = ProposalAdded(data=data)
            participants_ch.sync_publish(msg)


@receiver(channel_subscribed, sender=AgendaItemChannel)
def agenda_item_channel_subscribed(context: AgendaItem, app_state: AppState, **kw):
    """
    Populate app_state with TextDocuments
    """
    serializer = TextDocumentSerializer(
        TextDocument.objects.filter(agenda_item=context), many=True
    )
    for item in serializer.data:
        app_state.append(TextDocumentAdded(**item))


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
