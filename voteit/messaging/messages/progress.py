from typing import Optional

from pydantic import BaseModel
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.decorators import outgoing


# So should we have an initializer that's a special message, or simply
# have the first status update (and all subsequent ones) contain all information?


class ProgressSchema(BaseModel):
    curr: int
    total: int
    msg: Optional[str]


@outgoing
class ProgressNum(BaseOutgoingMessage):
    name = "progress.num"
    schema = ProgressSchema
    data: ProgressSchema
