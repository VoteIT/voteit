#from voteit.messaging.messages.abcs import AbstractOutgoingMessage
from pydantic import BaseModel
from voteit.messaging.registries import outgoing_messages
from voteit.messaging.abcs import BaseOutgoingMessage

# So should we have an initializer that's a special message, or simply
# have the first status update (and all subsequent ones) contain all information?
@outgoing_messages
class ProgressNum(BaseOutgoingMessage):
    name = "progress.num"

    class schema(BaseModel):
        curr: int
        total: int
        msg: str = ""
