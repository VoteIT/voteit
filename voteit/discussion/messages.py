from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from voteit.agenda.models import AgendaItem

from voteit.messaging.decorators import outgoing, incoming
from voteit.messaging.messages.base import (
    BaseObjectAdded,
    BaseObjectChanged,
    BaseObjectDeleted,
    BaseAddObject,
    BaseChangeObject,
    BaseDeleteObject,
)
from voteit.discussion.models import DiscussionPost
from voteit.discussion.permissions import DiscussionPermissions

User = get_user_model()


if TYPE_CHECKING:
    pass


@incoming
class AddDiscussionPost(BaseAddObject):
    name = "discussion_post.add"
    permission = DiscussionPermissions.ADD
    model = AgendaItem  # This is the context for the action!


@incoming
class ChangeDiscussionPost(BaseChangeObject):
    name = "discussion_post.change"
    model = DiscussionPost
    permission = DiscussionPermissions.CHANGE


@incoming
class DeleteDiscussionPost(BaseDeleteObject):
    name = "discussion_post.delete"
    model = DiscussionPost
    permission = DiscussionPermissions.DELETE


@outgoing
class DiscussionPostAdded(BaseObjectAdded):
    name = "discussion_post.added"


@outgoing
class DiscussionPostChanged(BaseObjectChanged):
    name = "discussion_post.changed"


@outgoing
class DiscussionPostDeleted(BaseObjectDeleted):
    name = "discussion_post.deleted"
