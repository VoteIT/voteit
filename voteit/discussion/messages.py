from typing import Literal
from voteit.messaging.decorators import outgoing
from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted


@outgoing
class DiscussionPostChanged(ObjectAddedOrChanged):
    action: Literal["discussion_post.changed"] = "discussion_post.changed"


@outgoing
class DiscussionPostDeleted(ObjectDeleted):
    action: Literal["discussion_post.deleted"] = "discussion_post.deleted"
