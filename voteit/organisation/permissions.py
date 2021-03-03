from voteit.core.permission import ModelPermissions
from voteit.core.permission import Permission as P


class OrgPermissions(ModelPermissions):
    model = "organisation"

    ADD = P("organisation.add_organisation")  # FIXME: We don't know about the context
    CHANGE = P("organisation.change_organisation")
    DELETE = P("organisation.delete_organisation")
    VIEW = P("organisation.view_organisation")
    MANAGE = P("organisation.manage_organisation")
