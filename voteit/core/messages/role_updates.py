from __future__ import annotations

from pydantic import validator
from pydantic.main import BaseModel

from envelope.core.message import Message
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

    @validator("roles", pre=True, each_item=True)
    def roles_to_str(cls, v: str | Role):
        if isinstance(v, Role):
            v = str(v)
        return v


@outgoing
class RolesAdded(Message):
    name = "roles.added"
    schema = RolesChangeSchema
    data: RolesChangeSchema


@outgoing
class RolesRemoved(Message):
    name = "roles.removed"
    schema = RolesChangeSchema
    data: RolesChangeSchema
