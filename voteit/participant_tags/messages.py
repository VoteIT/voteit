from envelope.core import Message
from pydantic.main import BaseModel

from voteit.messaging.decorators import outgoing


class ParticipantTagsSchema(BaseModel):
    meeting: int
    user: int
    tags: dict


@outgoing
class ParticipantTagsChanged(Message):
    """
    There's no deleted or added message for this tag. Deleted is simply empty tags.
    """

    name = "ptags.changed"
    schema = ParticipantTagsSchema
    data: ParticipantTagsSchema


class AllParticipantTagsSchema(BaseModel):
    tags: dict[str, list[int]]  # ns:tag [userid,...]
    meeting: int


@outgoing
class AllParticipantTags(Message):
    name = "ptags.all"
    schema = AllParticipantTagsSchema
    data: AllParticipantTagsSchema
