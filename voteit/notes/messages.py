from voteit.messaging.base import AddedOrUpdatedSchema
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import outgoing


class NoteAddedOrUpdatedSchema(AddedOrUpdatedSchema):
    created: str


@outgoing
class NoteAdded(BaseObjectAdded):
    name = "note.added"
    schema = NoteAddedOrUpdatedSchema
    data: NoteAddedOrUpdatedSchema


@outgoing
class NoteChanged(BaseObjectChanged):
    name = "note.changed"
    schema = NoteAddedOrUpdatedSchema
    data: NoteAddedOrUpdatedSchema


@outgoing
class NoteDeleted(BaseObjectDeleted):
    name = "note.deleted"
