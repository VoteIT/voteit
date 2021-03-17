from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class PresenceSystemPermissions(ModelPermissions):
    model = "presence_system"
    ADD = P("presence.add_presencesystem", context="meeting")
    CHANGE = P("presence.change_presencesystem")
    DELETE = P("presence.delete_presencesystem")
    VIEW = P("presence.view_presencesystem")


class PresenceCheckPermissions(ModelPermissions):
    model = "presence_check"
    ADD = P("presence.add_presencecheck", context="meeting")
    CHANGE = P("presence.change_presencecheck")
    DELETE = P("presence.delete_presencecheck")
    VIEW = P("presence.view_presencecheck")


class PresencePermissions(ModelPermissions):
    model = "presence"
    # Change doesn't exist
    ADD = P("presence.add_presence", context="presence_check")
    DELETE = P("presence.delete_presence")
    VIEW = P("presence.view_presence")
