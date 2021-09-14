from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.registries import outgoing_messages


@outgoing_messages
class StatusDone(BaseOutgoingMessage):
    name = "status.done"
