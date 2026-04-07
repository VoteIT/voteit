from __future__ import annotations
from typing import TYPE_CHECKING

import rules

from voteit.agenda.rules import ai_proposals_not_blocked
from voteit.agenda.rules import upcoming_ongoing_or_private_ai
from voteit.agenda.rules import upcoming_or_ongoing_ai
from voteit.core import PERM
from voteit.core.decorators import predicate
from voteit.core.rules import is_author_or_group_author_member
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_proposer
from voteit.proposal import PERM_RETRACT
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
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
# FIXME: There's a quirk with how REST framework viewset handles permissions with subclassed objects that
# exist in the database. (At least due to how we've done it)
# So some operations will be on DiffProposal and some will be on the parent Proposal object.
# So diff_proposal must be a valid context for the proposal permissions too

for pmodel in (Proposal, DiffProposal):
    rules.add_perm(
        pmodel.get_perm(PERM.ADD),
        (is_moderator & upcoming_ongoing_or_private_ai)
        | (upcoming_or_ongoing_ai & ai_proposals_not_blocked & is_proposer),
    )
    # View props not needed, managed by querysets
    rules.add_perm(
        pmodel.get_perm(PERM.CHANGE), upcoming_ongoing_or_private_ai & is_moderator
    )
    rules.add_perm(
        pmodel.get_perm(PERM.DELETE),
        is_not_used_in_poll & is_moderator & upcoming_ongoing_or_private_ai,
    )
    rules.add_perm(
        pmodel.get_perm(PERM_RETRACT),
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
    TextDocument.get_perm(PERM.ADD),
    is_moderator & upcoming_ongoing_or_private_ai,
)
rules.add_perm(
    TextDocument.get_perm(PERM.CHANGE),
    upcoming_ongoing_or_private_ai & is_moderator & has_no_proposals,
)
rules.add_perm(
    TextDocument.get_perm(PERM.DELETE),
    is_moderator & upcoming_ongoing_or_private_ai & has_no_proposals,
)
