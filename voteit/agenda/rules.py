import rules
from django.contrib.auth.models import AbstractUser

from voteit.agenda.models import AgendaItem
from voteit.agenda.workflows import AgendaItemWf
from voteit.core import PERM
from voteit.core.abcs import AgendaItemContext
from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived, is_not_private
from voteit.meeting.rules import is_moderator, can_view_meeting


@predicate
def upcoming_or_ongoing_ai(user: AbstractUser, context: AgendaItemContext):
    return (
        isinstance(context, AgendaItemContext)
        and context.agenda_item is not None
        and context.agenda_item.state
        in (
            AgendaItemWf.UPCOMING,
            AgendaItemWf.ONGOING,
        )
    )


@predicate
def upcoming_ongoing_or_private_ai(user: AbstractUser, context: AgendaItemContext):
    """For moderators basically"""
    return (
        isinstance(context, AgendaItemContext)
        and context.agenda_item is not None
        and context.agenda_item.state
        in (AgendaItemWf.UPCOMING, AgendaItemWf.ONGOING, AgendaItemWf.PRIVATE)
    )


@predicate
def can_view_ai(user: AbstractUser, context: AgendaItemContext) -> bool:
    """Shorthand for checks that decide if related agenda item can be viewed"""

    if not isinstance(context, AgendaItemContext):
        raise TypeError(f"Expected AgendaItemContext, got {type(context)}")
    return is_moderator(user, context.agenda_item) or (
        is_not_private(user, context.agenda_item)
        and can_view_meeting(user, context.agenda_item)
    )


@predicate
def ai_discussion_not_blocked(user: AbstractUser, context: AgendaItemContext) -> bool:
    return (
        isinstance(context, AgendaItemContext)
        and context.agenda_item is not None
        and not context.agenda_item.block_discussion
    )


@predicate
def ai_proposals_not_blocked(user: AbstractUser, context: AgendaItemContext) -> bool:
    return (
        isinstance(context, AgendaItemContext)
        and context.agenda_item is not None
        and not context.agenda_item.block_proposals
    )


@predicate
def ai_not_archived(user: AbstractUser, context: AgendaItemContext) -> bool:
    return isinstance(context, AgendaItemContext) and is_not_archived(
        user, context.agenda_item
    )


@predicate
def ai_not_private(user: AbstractUser, context: AgendaItemContext) -> bool:
    return isinstance(context, AgendaItemContext) and is_not_private(
        user, context.agenda_item
    )


rules.add_perm(
    AgendaItem.get_perm(PERM.ADD), is_not_archived & is_moderator
)  # Checked against meeting!
# Used by messages too, so queryset check isn't enough
rules.add_perm(AgendaItem.get_perm(PERM.VIEW), can_view_ai)
rules.add_perm(AgendaItem.get_perm(PERM.CHANGE), is_not_archived & is_moderator)
rules.add_perm(AgendaItem.get_perm(PERM.DELETE), is_not_archived & is_moderator)
