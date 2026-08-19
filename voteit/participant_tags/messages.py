from typing import Literal
from chanx.messages.base import BaseMessage
from pydantic.main import BaseModel

from voteit.messaging.decorators import outgoing


class ParticipantTagsSchema(BaseModel):
    meeting: int
    user: int
    tags: dict


@outgoing
class ParticipantTagsChanged(BaseMessage):
    """
    There's no deleted or added message for this tag. Deleted is simply empty tags.
    """

    action: Literal["ptags.changed"] = "ptags.changed"
    payload: ParticipantTagsSchema


class AllParticipantTagsSchema(BaseModel):
    tags: dict[str, list[int]]  # ns:tag [userid,...]
    meeting: int


@outgoing
class AllParticipantTags(BaseMessage):
    action: Literal["ptags.all"] = "ptags.all"
    payload: AllParticipantTagsSchema
