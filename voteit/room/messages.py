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


@outgoing
class RoomHighlightedProposals(BaseObjectChanged):
    name = "room.props"


@outgoing
class RoomDeleted(BaseObjectDeleted):
    name = "room.deleted"
