from voteit.messaging.messages.base import BaseObjectAdded, BaseObjectChanged, BaseObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class AgendaAdded(BaseObjectAdded):
    name = "agenda.added"


@outgoing
class AgendaChanged(BaseObjectChanged):
    name = "agenda.changed"


@outgoing
class AgendaDeleted(BaseObjectDeleted):
    name = "agenda.deleted"
