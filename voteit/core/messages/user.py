from typing import Literal
from chanx.messages.base import BaseMessage
from pydantic import BaseModel


from voteit.messaging.decorators import outgoing


class UserPKSchema(BaseModel):
    pk: int


@outgoing
class InvalidateUserCache(BaseMessage):
    action: Literal["user.inv"] = "user.inv"
    payload: UserPKSchema
