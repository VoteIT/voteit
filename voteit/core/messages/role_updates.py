from __future__ import annotations

from typing import Literal
from chanx.messages.base import BaseMessage

from pydantic import field_validator
from pydantic.main import BaseModel

from voteit.core.role import Role
from voteit.messaging.decorators import outgoing


class RolesChangeSchema(BaseModel):
    """
    Roles changed, either added or removed.

    model is the class name an pk the primary key of the context where the change happened.
    """

    user_pk: int
    roles: list[str]
    pk: int  # context where the change happened, use together with model
    model: str  # The model shortname

    @field_validator("roles", mode="before")
    @classmethod
    def roles_to_str(cls, v):
        if isinstance(v, (list, tuple, set)):
            return [str(item) if isinstance(item, Role) else item for item in v]
        return v


@outgoing
class RolesChanged(BaseMessage):
    action: Literal["roles.changed"] = "roles.changed"
    payload: RolesChangeSchema


@outgoing
class RolesRemoved(BaseMessage):
    action: Literal["roles.removed"] = "roles.removed"
    payload: RolesChangeSchema
