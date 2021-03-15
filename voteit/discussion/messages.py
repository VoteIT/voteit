from __future__ import annotations

from typing import TYPE_CHECKING

# from django.contrib.auth import get_user_model

from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted


if TYPE_CHECKING:
    pass
    # from django.contrib.auth.models import AbstractUser


# User: AbstractUser = get_user_model()

# @incoming
# class AddDiscussionPost(BaseAddObject):
#     name = "discussion_post.add"
#     permission = DiscussionPermissions.ADD
#     model = AgendaItem  # This is the context for the action!
#     add_model = DiscussionPost
#     relation_queryset_attribute = "discussions"
#
#
# @incoming
# class ChangeDiscussionPost(BaseChangeObject):
#     name = "discussion_post.change"
#     model = DiscussionPost
#     permission = DiscussionPermissions.CHANGE
#
#
# @incoming
# class DeleteDiscussionPost(BaseDeleteObject):
#     name = "discussion_post.delete"
#     model = DiscussionPost
#     permission = DiscussionPermissions.DELETE


@outgoing
class DiscussionPostAdded(BaseObjectAdded):
    name = "discussion_post.added"


@outgoing
class DiscussionPostChanged(BaseObjectChanged):
    name = "discussion_post.changed"


@outgoing
class DiscussionPostDeleted(BaseObjectDeleted):
    name = "discussion_post.deleted"
