from voteit.messaging.messages.abcs import AbstractOutgoingMessage
from voteit.messaging.registries import websocket_outgoing_messages

# FIXME: This is a stub

@websocket_outgoing_messages("agenda.changed")
class AgendaUpdated(AbstractOutgoingMessage):
    items: list


@websocket_outgoing_messages("agenda.deleted")
class AgendaDeleted(AbstractOutgoingMessage):
    items: list
