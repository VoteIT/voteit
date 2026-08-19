from __future__ import annotations

from pydantic import validator
from pydantic.main import BaseModel

from envelope.core.message import Message
from voteit.core.validators import validate_model_shortname
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class ButtonAdded(BaseObjectAdded):
    name = "reaction_button.added"


@outgoing
class ButtonChanged(BaseObjectChanged):
    name = "reaction_button.changed"


@outgoing
class ButtonDeleted(BaseObjectDeleted):
    name = "reaction_button.deleted"


class ReactionSchema(BaseModel):
    content_type: str
    object_id: int
    button: int

    @validator("content_type")
    def validate_content_type(cls, v):
        return validate_model_shortname(v)


class ReactionCountSchema(ReactionSchema):
    count: int


class UserReactionResponseSchema(ReactionSchema):
    pk: int  # The reactions' pk!
    user: int
    agenda_item: int | None = None


@outgoing
class ReactionCount(Message):
    name = "reaction.count"
    schema = ReactionCountSchema
    data: ReactionCountSchema


@outgoing
class UserReactionAdded(Message):
    """
    Normally only sent to the user who added it!
    """

    name = "reaction.added"
    schema = UserReactionResponseSchema
    data: UserReactionResponseSchema


@outgoing
class UserReactionDeleted(BaseObjectDeleted):
    name = "reaction.deleted"
