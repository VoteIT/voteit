from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class AgendaPermissions(ModelPermissions):
    model = "agenda_item"

    ADD = P("agenda.add_agendaitem", context="meeting")
    CHANGE = P("agenda.change_agendaitem")
    DELETE = P("agenda.delete_agendaitem")
    VIEW = P("agenda.view_agendaitem")
