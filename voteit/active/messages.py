from typing import Literal
from chanx.messages.base import BaseMessage
from pydantic import BaseModel


from voteit.messaging.decorators import outgoing


class ActiveUserChangedSchema(BaseModel):
    meeting: int
    user: int
    active: bool


@outgoing
class ActiveUserChanged(BaseMessage):
    action: Literal["active_user.changed"] = "active_user.changed"
    payload: ActiveUserChangedSchema


class ActiveUsersSchema(BaseModel):
    meeting: int
    users: list[int]


@outgoing
class ActiveUsers(BaseMessage):
    action: Literal["active_user.all"] = "active_user.all"
    payload: ActiveUsersSchema
