from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class PresenceCheckPermissions(ModelPermissions):
    model = "presence_check"
    ADD = P("presence.add_presencecheck", context="meeting")
    CHANGE = P("presence.change_presencecheck")
    DELETE = P("presence.delete_presencecheck")
    VIEW = P("presence.view_presencecheck")


class PresencePermissions(ModelPermissions):
    model = "presence"
    CHANGE = P("presence.change_presence", context="presence_check")
    VIEW = P("presence.view_presence")
