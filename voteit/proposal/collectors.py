from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.proposal.diff import Changes
from voteit.proposal.messages import ProposalChanged
from voteit.proposal.messages import TextDocumentChanged
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.rest_api.serializers import DiffProposalDetailSerializer
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer
from voteit.proposal.rest_api.serializers import TextDocumentSerializer

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.messaging.state import AppState


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
    exclude_fields = {"body_diff_brief", "shortname", "mentions"}
    proposal_fields = set(ProposalDetailSerializer.Meta.fields) - exclude_fields
    qs = Proposal.objects.filter(
        agenda_item__meeting=meeting, diffproposal__isnull=True
    )
    if not include_private:
        qs = qs.exclude(agenda_item__state=AgendaItemStateMachine.private.value)
    payloads = []
    shortname = get_model_shortname(Proposal)
    items = list(qs.values(*proposal_fields))
    mentions_map = _fetch_mentions_map([item["pk"] for item in items])
    for item in items:
        item["m"] = meeting.pk
        item["shortname"] = shortname
        item["mentions"] = mentions_map.get(item["pk"], [])
        payloads.append(item)

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
        payloads.append(item)

    app_state.add_batch(ProposalChanged, payloads)


@app_state_collectors
class Proposals(AppStateCollector):
    """Every proposal in the meeting, plain and diff, as one batch.

    Private agenda items are only included on the moderator channel.
    """

    name = "proposal.proposals"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 50

    def collect(self, state: AppState) -> None:
        attach_proposals(
            self.context,
            state,
            include_private=isinstance(self.channel, ModeratorsChannel),
        )


@app_state_collectors
class TextDocuments(AppStateCollector):
    name = "proposal.text_documents"
    channels = (AgendaItemChannel,)
    order = 50

    def collect(self, state: AppState) -> None:
        state.add_batch(
            TextDocumentChanged,
            TextDocumentSerializer(
                TextDocument.objects.filter(agenda_item=self.context), many=True
            ).data,
        )
