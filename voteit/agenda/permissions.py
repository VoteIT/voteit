from voteit.core.registries import permissions


class AgendaPermissions:
    ADD = permissions.create("voteit.agenda.add_agenda", "meeting.Meeting")
    CHANGE = permissions.create("voteit.agenda.change_agenda", "agenda.AgendaItem")
    DELETE = permissions.create("voteit.agenda.delete_agenda", "agenda.AgendaItem")
    VIEW = permissions.create("voteit.agenda.view_agenda", "agenda.AgendaItem")
