from voteit.messaging.messages.abcs import AbstractOutgoingMessage
from voteit.messaging.registries import websocket_outgoing_messages


@websocket_outgoing_messages
class TextMessage(AbstractOutgoingMessage):
    """ A"""
    message: str = ""
