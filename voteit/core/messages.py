from pydantic.main import BaseModel
from typing import List

from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.decorators import outgoing


class RolesChangeSchema(BaseModel):
    """
    Roles changed, either added or removed.

    model is the class name an pk the primary key of the context where the change happened.
    """

    user_pk: int
    roles: List[str]
    pk: int  # context where the change happened, use together with model
    model: str  # The model shortname


@outgoing
class RolesAdded(BaseOutgoingMessage):
    name = "roles.added"
    schema = RolesChangeSchema
    data: RolesChangeSchema


@outgoing
class RolesRemoved(BaseOutgoingMessage):
    name = "roles.removed"
    schema = RolesChangeSchema
    data: RolesChangeSchema
