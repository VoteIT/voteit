from voteit.core.registries import permissions


class AgendaPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.agenda.models import AgendaItem
    >>> find_bad_permission_names(AgendaPermissions, AgendaItem)

    """

    ADD = permissions.create("agenda.add_agendaitem", "meeting.Meeting")
    CHANGE = permissions.create("agenda.change_agendaitem", "agenda.AgendaItem")
    DELETE = permissions.create("agenda.delete_agendaitem", "agenda.AgendaItem")
    VIEW = permissions.create("agenda.view_agendaitem", "agenda.AgendaItem")
