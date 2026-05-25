from pydantic import BaseModel

from envelope.core.message import Message

from voteit.messaging.decorators import outgoing


class ActiveUserChangedSchema(BaseModel):
    meeting: int
    user: int
    active: bool


@outgoing
class ActiveUserChanged(Message):
    name = "active_user.changed"
    schema = ActiveUserChangedSchema
    data: ActiveUserChangedSchema


class ActiveUsersSchema(BaseModel):
    meeting: int
    users: list[int]


@outgoing
class ActiveUsers(Message):
    name = "active_user.all"
    schema = ActiveUsersSchema
    data: ActiveUsersSchema
