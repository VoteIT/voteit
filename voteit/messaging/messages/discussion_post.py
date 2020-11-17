from voteit.messaging.messages.abcs import AbstractOutgoingMessage
from voteit.messaging.registries import websocket_outgoing_messages


# FIXME: This is a stub

@websocket_outgoing_messages("discussion_post.changed")
class DiscussionPostUpdated(AbstractOutgoingMessage):
    items: list


@websocket_outgoing_messages("discussion_post.deleted")
class DiscussionPostDeleted(AbstractOutgoingMessage):
    items: list
