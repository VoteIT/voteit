import rules
from django.contrib.auth.models import AbstractUser

from voteit.agenda.models import AgendaItem
from voteit.agenda.rules import is_non_private_ai
from voteit.core.rules import is_not_finished
from voteit.core.rules import is_author
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_participant
from voteit.meeting.rules import is_proposer
from voteit.meeting.rules import is_public
from voteit.proposal.models import Proposal
from voteit.proposal.permissions import ProposalPermissions
from voteit.proposal.workflows import ProposalWf


def is_not_proposal_blocked(user: AbstractUser, agenda_item: AgendaItem):
    return isinstance(agenda_item, AgendaItem) and not agenda_item.block_proposals


def is_not_used_in_poll(user: AbstractUser, proposal: Proposal):
    return isinstance(proposal, Proposal) and proposal.polls.count() == 0


def is_published(user: AbstractUser, proposal: Proposal):
    return isinstance(proposal, Proposal) and proposal.state == ProposalWf.PUBLISHED


def can_add_proposal(user: AbstractUser, agenda_item: AgendaItem):
    """ Moderators can always add in agenda items that aren't closed. """
    if isinstance(agenda_item, AgendaItem) and is_not_finished(user, agenda_item):
        return is_moderator(user, agenda_item.meeting) or (
            is_non_private_ai(user, agenda_item)
            and is_not_proposal_blocked(user, agenda_item)
            and is_proposer(user, agenda_item.meeting)
        )


def can_view_proposal(user: AbstractUser, proposal: Proposal):
    """ Currently discussions can't exist outside of agenda items and meeting. That might change.
    """
    try:
        meeting = proposal.agenda_item.meeting  # Will catch None too
    except AttributeError:  # pragma: no cover
        return
    return (
        is_moderator(user, meeting)
        or is_non_private_ai(user, proposal.agenda_item)
        and (is_participant(user, meeting) or is_public(user, meeting))
    )


def can_change_proposal(user: AbstractUser, proposal: Proposal):
    """ Users have traditionally not been able to change their posts in voteit. This should perhaps change.
    """
    # FIXME: Do we want versioning and allow changes here?
    try:
        meeting = proposal.agenda_item.meeting  # Will catch None too
    except AttributeError:  # pragma: no coverage
        return
    return is_not_finished(user, meeting) and is_moderator(user, meeting)


def can_delete_proposal(user: AbstractUser, proposal: Proposal):
    try:
        meeting = proposal.agenda_item.meeting  # Will catch None too
    except AttributeError:  # pragma: no coverage
        return
    return (
        is_not_used_in_poll(user, proposal)
        and is_not_finished(user, meeting)
        and is_moderator(user, meeting)
    )


def can_retract_proposal(user: AbstractUser, proposal: Proposal):
    try:
        meeting = proposal.agenda_item.meeting  # Will catch None too
    except AttributeError:  # pragma: no coverage
        return

    # Moderator-check - allow edit on non-finished meetings
    if is_moderator(user, meeting):
        return is_not_finished(user, meeting)
    # User-check, least expensive checks first please!
    return (
        is_published(user, proposal)
        and is_author(user, proposal)
        and is_not_proposal_blocked(user, proposal.agenda_item)
        and is_not_finished(user, proposal.agenda_item)
        and is_non_private_ai(user, proposal.agenda_item)
    )


rules.add_perm(ProposalPermissions.ADD, can_add_proposal)
rules.add_perm(ProposalPermissions.VIEW, can_view_proposal)
rules.add_perm(ProposalPermissions.CHANGE, can_change_proposal)
rules.add_perm(ProposalPermissions.DELETE, can_delete_proposal)
rules.add_perm(ProposalPermissions.RETRACT, can_retract_proposal)
