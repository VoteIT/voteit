from typing import Literal
from chanx.messages.base import BaseMessage
from pydantic import BaseModel
from pydantic import model_validator


from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class RoomChanged(ObjectAddedOrChanged):
    action: Literal["room.changed"] = "room.changed"


class RoomHighlightedSchema(BaseModel):
    pk: int
    highlighted: list[int]
    token: str | None = None


@outgoing
class RoomHighlighted(BaseMessage):
    action: Literal["room.highlighted"] = "room.highlighted"
    payload: RoomHighlightedSchema


@outgoing
class RoomDeleted(ObjectDeleted):
    action: Literal["room.deleted"] = "room.deleted"


class RoomMarkTextSchema(BaseModel):
    """
    >>> S = RoomMarkTextSchema
    >>> S(room=1).model_dump(exclude_unset=True)
    {'room': 1}

    >>> S(proposal=1, start=1, end=2, room=1).model_dump(exclude_unset=True)
    {'room': 1, 'start': 1, 'end': 2, 'proposal': 1}

    >>> S(proposal=1, room=1).model_dump(exclude_unset=True)
    {'room': 1, 'proposal': 1}

    >>> S(start=1, end=2, room=1).model_dump(exclude_unset=True)
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:

    >>> S(start=1, proposal=1, room=1).model_dump(exclude_unset=True)
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:
    """

    room: int
    start: int | None = None
    end: int | None = None
    proposal: int | None = None

    # One model validator rather than two field validators with always=True:
    # v2 field validators never run when a field falls back to its default, so
    # the "start without end" and "start without proposal" cases would stop
    # raising entirely.
    @model_validator(mode="after")
    def validate_marking(self):
        if type(self.end) is not type(self.start):
            raise ValueError("Both start and end must be a number or None")
        if isinstance(self.start, int):
            if not self.start < self.end:
                raise ValueError("end must be higher than start")
            if not isinstance(self.proposal, int):
                raise ValueError("proposal must be specified if start and end is set")
        return self


@outgoing
class RoomMarked(BaseMessage):
    action: Literal["room.marked"] = "room.marked"
    payload: RoomMarkTextSchema
