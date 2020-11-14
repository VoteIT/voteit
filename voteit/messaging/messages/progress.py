from voteit.messaging.messages.abcs import AbstractOutgoingMessage
from voteit.messaging.registries import websocket_outgoing_messages

# So should we have an initializer that's a special message, or simply
# have the first status update (and all subsequent ones) contain all information?

@websocket_outgoing_messages("progress.num")
class ProgressNum(AbstractOutgoingMessage):
    curr: int
    total: int
    msg: str = ""
