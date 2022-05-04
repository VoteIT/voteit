from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class AutomaticAccessPermissions(ModelPermissions):
    model = "automatic"

    ADD = P("access_policy.add_automaticaccess", context="meeting")
    CHANGE = P("access_policy.change_automaticaccess")
    DELETE = P("access_policy.delete_automaticaccess")
    VIEW = P("access_policy.view_automaticaccess")
