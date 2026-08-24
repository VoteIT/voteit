from typing import Literal
from voteit.messaging.base import AddedOrUpdatedSchema
from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


class NoteAddedOrUpdatedSchema(AddedOrUpdatedSchema):
    created: str


@outgoing
class NoteChanged(ObjectAddedOrChanged):
    action: Literal["note.changed"] = "note.changed"
    payload: NoteAddedOrUpdatedSchema


@outgoing
class NoteDeleted(ObjectDeleted):
    action: Literal["note.deleted"] = "note.deleted"
