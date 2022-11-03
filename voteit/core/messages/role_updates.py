from __future__ import annotations

from pydantic.main import BaseModel

from envelope.core.message import Message
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
