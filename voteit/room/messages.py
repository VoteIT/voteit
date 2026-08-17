from pydantic import BaseModel
from pydantic import validator

from envelope.core import Message

from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class RoomAdded(BaseObjectAdded):
    name = "room.added"


@outgoing
class RoomChanged(BaseObjectChanged):
    name = "room.changed"


class RoomHighlightedSchema(BaseModel):
    pk: int
    highlighted: list[int]
    token: str | None = None


@outgoing
class RoomHighlighted(Message):
    name = "room.highlighted"
    schema = RoomHighlightedSchema
    data: RoomHighlightedSchema


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

    >>> S(proposal=1, room=1).dict(exclude_unset=True)
    {'room': 1, 'proposal': 1}

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
        if type(v) is not type(start):
            raise ValueError("Both start and end must be a number or None")
        if isinstance(start, int) and not start < v:
            raise ValueError("end must be higher than start")
        return v

    @validator("proposal", always=True)
    def validate_proposal(cls, v: int | None, values: dict):
        start = values.get("start")
        if isinstance(start, int) and not isinstance(v, int):
            raise ValueError("proposal must be specified if start and end is set")
        return v


@outgoing
class RoomMarked(Message):
    name = "room.marked"
    schema = RoomMarkTextSchema
    data: RoomMarkTextSchema
