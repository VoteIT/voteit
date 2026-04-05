from voteit.messaging.decorators import outgoing
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted


@outgoing
class DiscussionPostAdded(BaseObjectAdded):
    name = "discussion_post.added"


@outgoing
class DiscussionPostChanged(BaseObjectChanged):
    name = "discussion_post.changed"


@outgoing
class DiscussionPostDeleted(BaseObjectDeleted):
    name = "discussion_post.deleted"
