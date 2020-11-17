from voteit.messaging.messages.abcs import ObjectAdded, ObjectChanged, ObjectDeleted
from voteit.messaging.registries import websocket_outgoing_messages


@websocket_outgoing_messages("agenda.added")
class AgendaAdded(ObjectAdded):
    pass


@websocket_outgoing_messages("agenda.changed")
class AgendaChanged(ObjectChanged):
    pass


@websocket_outgoing_messages("agenda.deleted")
class AgendaDeleted(ObjectDeleted):
    pass
