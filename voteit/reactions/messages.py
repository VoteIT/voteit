from __future__ import annotations

from typing import Literal
from chanx.messages.base import BaseMessage

from pydantic import field_validator
from pydantic.main import BaseModel

from voteit.core.validators import validate_model_shortname
from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class ButtonChanged(ObjectAddedOrChanged):
    action: Literal["reaction_button.changed"] = "reaction_button.changed"


@outgoing
class ButtonDeleted(ObjectDeleted):
    action: Literal["reaction_button.deleted"] = "reaction_button.deleted"


class ReactionSchema(BaseModel):
    content_type: str
    object_id: int
    button: int

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v):
        return validate_model_shortname(v)


class ReactionCountSchema(ReactionSchema):
    count: int


class UserReactionResponseSchema(ReactionSchema):
    pk: int  # The reactions' pk!
    user: int
    agenda_item: int | None = None


@outgoing
class ReactionCount(BaseMessage):
    action: Literal["reaction.count"] = "reaction.count"
    payload: ReactionCountSchema


@outgoing
class UserReactionAdded(BaseMessage):
    """
    Normally only sent to the user who added it!
    """

    action: Literal["reaction.changed"] = "reaction.changed"
    payload: UserReactionResponseSchema


@outgoing
class UserReactionDeleted(ObjectDeleted):
    action: Literal["reaction.deleted"] = "reaction.deleted"
