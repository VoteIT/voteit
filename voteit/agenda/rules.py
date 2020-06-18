import rules
from django.contrib.auth.models import User
from voteit.agenda.models import AgendaItem
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.rules import is_not_archived
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rules import is_moderator
from voteit.agenda.permissions import AgendaPermissions


def is_non_private_ai(user: User, agenda_item: AgendaItem):
    # Keep negated state here since it might be called with agenda_item as None!
    return (
        isinstance(agenda_item, AgendaItem)
        and agenda_item.state != AgendaItemWf.PRIVATE
    )


# object permissions
@rules.predicate
def can_view_agenda(user: User, agenda_item: AgendaItem):
    if isinstance(agenda_item, AgendaItem):
        if is_non_private_ai(user, agenda_item):
            return user.has_perm(MeetingPermissions.VIEW, agenda_item.meeting)
        return is_moderator(user, agenda_item.meeting)


@rules.predicate
def can_moderate_agendas_meeting(user: User, agenda_item: AgendaItem):
    """ Delegated to meeting moderator, which checks for archived too. """
    return (
        isinstance(agenda_item, AgendaItem)
        and is_not_archived(user, agenda_item)
        and user.has_perm(MeetingPermissions.MODERATE, agenda_item.meeting)
    )


rules.add_perm(
    AgendaPermissions.ADD, is_not_archived & is_moderator
)  # Checked against meeting!
rules.add_perm(AgendaPermissions.VIEW, can_view_agenda)
rules.add_perm(AgendaPermissions.CHANGE, can_moderate_agendas_meeting)
rules.add_perm(AgendaPermissions.DELETE, can_moderate_agendas_meeting)
