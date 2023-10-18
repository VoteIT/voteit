from pydantic import BaseModel

from envelope.core.message import Message

from voteit.messaging.decorators import outgoing


class UserPKSchema(BaseModel):
    pk: int


@outgoing
class InvalidateUserCache(Message):
    name = "user.inv"
    schema = UserPKSchema
    data: UserPKSchema
