from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class ActiveUserPermissions(ModelPermissions):
    model = "active_user"
    CHANGE = P("active.change_activeuser", context={"meeting"})
    VIEW = P("active.view_activeuser", context={"meeting"})
