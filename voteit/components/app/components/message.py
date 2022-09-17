from pydantic import BaseModel

from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import organisation_components
from voteit.components.registries import meeting_components


class MessageSchema(BaseModel):
    msg: str
    type: str = "info"


@organisation_components
@meeting_components
class FlashMessage(ComponentAdapter):
    """
    An announcement or similar
    """

    name = "flash_message"
    title = "Flash message"
    multiple = True
    schema = MessageSchema
