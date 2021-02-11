from pydantic.main import BaseModel
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import (
    BaseObjectAdded,
    BaseObjectChanged,
    BaseObjectDeleted,
)


@outgoing
class ButtonAdded(BaseObjectAdded):
    name = "reaction_button.added"


@outgoing
class ButtonChanged(BaseObjectChanged):
    name = "reaction_button.changed"


@outgoing
class ButtonDeleted(BaseObjectDeleted):
    name = "reaction_button.deleted"


class ReactionCountSchema(BaseModel):
    content_type: int
    object_id: int
    button: int
    count: int


@outgoing
class ReactionCount(BaseOutgoingMessage):
    name = "reaction.count"
    schema = ReactionCountSchema
    data: ReactionCountSchema


class UserReactionSchema(BaseModel):
    pk: int
    content_type: int
    object_id: int
    button: int
    user: int
    agenda_item: int


@outgoing
class UserReactionAdded(BaseOutgoingMessage):
    """ Normally only sent to the user who added it!"""

    name = "reaction.added"
    schema = UserReactionSchema
    data: UserReactionSchema


# FIXME
# @outgoing
# class UserReactionDeleted(BaseObjectDeleted):
#     name = "reaction.deleted"


# FIXME: Add/delete
