from voteit.messaging.messages.abcs import ObjectAdded, ObjectChanged, ObjectDeleted, AbstractOutgoingMessage
from voteit.messaging.registries import websocket_outgoing_messages


@websocket_outgoing_messages("poll.added")
class PollAdded(ObjectAdded):
    pass


@websocket_outgoing_messages("poll.changed")
class PollChanged(ObjectChanged):
    pass


@websocket_outgoing_messages("poll.deleted")
class PollDeleted(ObjectDeleted):
    pass


@websocket_outgoing_messages("poll.status")
class PollStatus(AbstractOutgoingMessage):
    pk: int
    voted: int
    total: int
