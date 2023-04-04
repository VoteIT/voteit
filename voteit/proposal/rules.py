from __future__ import annotations
from typing import TYPE_CHECKING

import rules

from voteit.agenda.rules import ai_proposals_not_blocked
from voteit.agenda.rules import can_view_ai
from voteit.agenda.rules import upcoming_ongoing_or_private_ai
from voteit.agenda.rules import upcoming_or_ongoing_ai
from voteit.core.decorators import predicate
from voteit.core.rules import is_author_or_group_author_member
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_proposer
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.permissions import DiffProposalPermissions
from voteit.proposal.permissions import ProposalPermissions
from voteit.proposal.permissions import TextDocumentPermissions
from voteit.proposal.workflows import ProposalWf

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


@predicate
def is_not_used_in_poll(user: AbstractUser, proposal: Proposal):
    return isinstance(proposal, Proposal) and proposal.polls.count() == 0


@predicate
def is_published(user: AbstractUser, proposal: Proposal):
    return isinstance(proposal, Proposal) and proposal.state == ProposalWf.PUBLISHED


@predicate
def has_no_proposals(user: AbstractUser, text_document: TextDocument):
    return (
        isinstance(text_document, TextDocument)
        and not text_document.text_paragraphs.all()
        .filter(proposals__isnull=False)
        .exists()
    )


# Proposal and variants
# make sure diff and regular proposals work exactly the same!
for perm in (ProposalPermissions.ADD, DiffProposalPermissions.ADD):
    rules.add_perm(
        perm,
        (is_moderator & upcoming_ongoing_or_private_ai)
        | (upcoming_or_ongoing_ai & ai_proposals_not_blocked & is_proposer),
    )
for perm in (ProposalPermissions.VIEW, DiffProposalPermissions.VIEW):
    rules.add_perm(perm, can_view_ai)
for perm in (ProposalPermissions.CHANGE, DiffProposalPermissions.CHANGE):
    rules.add_perm(perm, upcoming_ongoing_or_private_ai & is_moderator)
for perm in (ProposalPermissions.DELETE, DiffProposalPermissions.DELETE):
    rules.add_perm(
        perm,
        is_not_used_in_poll & is_moderator & upcoming_ongoing_or_private_ai,
    )
for perm in (ProposalPermissions.RETRACT, DiffProposalPermissions.RETRACT):
    rules.add_perm(
        perm,
        (is_moderator & upcoming_ongoing_or_private_ai)
        | (
            upcoming_or_ongoing_ai
            & is_published
            & is_author_or_group_author_member
            & is_proposer
            & ai_proposals_not_blocked
        ),
    )


# TextDocument
rules.add_perm(
    TextDocumentPermissions.ADD,
    is_moderator & upcoming_ongoing_or_private_ai,
)
rules.add_perm(TextDocumentPermissions.VIEW, can_view_ai)
rules.add_perm(
    TextDocumentPermissions.CHANGE,
    upcoming_ongoing_or_private_ai & is_moderator & has_no_proposals,
)
rules.add_perm(
    TextDocumentPermissions.DELETE,
    is_moderator & upcoming_ongoing_or_private_ai & has_no_proposals,
)
