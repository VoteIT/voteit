from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class RoomPermissions(ModelPermissions):
    model = "room"
    ADD = P("room.add_room", context={"meeting"})
    CHANGE = P("room.change_room")
    DELETE = P("room.delete_room")
    VIEW = P("room.view_room")
