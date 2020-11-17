from voteit.messaging.messages.abcs import ObjectAdded, ObjectChanged, ObjectDeleted
from voteit.messaging.registries import websocket_outgoing_messages


@websocket_outgoing_messages("discussion_post.added")
class DiscussionPostAdded(ObjectAdded):
    pass


@websocket_outgoing_messages("discussion_post.changed")
class DiscussionPostChanged(ObjectChanged):
    pass


@websocket_outgoing_messages("discussion_post.deleted")
class DiscussionPostDeleted(ObjectDeleted):
    pass
