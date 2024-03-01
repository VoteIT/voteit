from pydantic import BaseModel
from pydantic import validator

from envelope.core import Message
from envelope.deferred_jobs.message import ContextAction
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.room.channels import RoomChannel
from voteit.room.models import Room
from voteit.room.permissions import RoomPermissions


@outgoing
class RoomAdded(BaseObjectAdded):
    name = "room.added"


@outgoing
class RoomChanged(BaseObjectChanged):
    name = "room.changed"


@outgoing
class RoomHighlighted(BaseObjectChanged):
    name = "room.highlighted"


@outgoing
class RoomDeleted(BaseObjectDeleted):
    name = "room.deleted"


class RoomMarkTextSchema(BaseModel):
    """
    >>> S = RoomMarkTextSchema
    >>> S(room=1).dict(exclude_unset=True)
    {'room': 1}

    >>> S(proposal=1, start=1, end=2, room=1).dict(exclude_unset=True)
    {'room': 1, 'start': 1, 'end': 2, 'proposal': 1}

    >>> S(start=1, end=2, room=1).dict(exclude_unset=True)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:

    >>> S(start=1, proposal=1, room=1).dict(exclude_unset=True)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:
    """

    room: int
    start: int | None = None
    end: int | None = None
    proposal: int | None = None

    @validator("end", always=True)
    def validate_start_end(cls, v: int | None, values: dict):
        start = values.get("start")
        if type(v) != type(start):
            raise ValueError("Both start and end must be a number or None")
        if isinstance(start, int) and not start < v:
            raise ValueError("end must be higher than start")
        return v

    @validator("proposal", always=True)
    def validate_proposal(cls, v: int | None, values: dict):
        start = values.get("start")
        if type(v) != type(start):
            raise ValueError("proposal must be the same type as start and end")
        return v


@incoming
class RoomMarkText(ContextAction):
    context_schema_attr = "room"
    name = "room.mark_text"
    permission = RoomPermissions.HANDLE
    model = Room
    schema = RoomMarkTextSchema
    data: RoomMarkTextSchema

    def run_job(self):
        # We won't raise errors or send responses for these kind of messages
        # since that will only be annoying for moderators
        if self.allowed():
            ch = RoomChannel.from_instance(self.context)
            msg = RoomMarked.from_message(self, **self.data.dict())
            ch.sync_publish(msg, on_commit=False)
            # No effect but might be nice for testing
            return msg


@outgoing
class RoomMarked(Message):
    name = "room.marked"
    schema = RoomMarkTextSchema
    data: RoomMarkTextSchema
