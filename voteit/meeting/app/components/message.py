from pydantic import BaseModel

from voteit.meeting.abcs import MeetingComponentAdapter
from voteit.meeting.registries import meeting_components


class MessageSchema(BaseModel):
    msg: str
    type: str = "info"


@meeting_components
class FlashMessage(MeetingComponentAdapter):
    """
    An announcement or similar
    """

    name = "flash_message"
    title = "Flash message"
    multiple = True
    schema = MessageSchema
