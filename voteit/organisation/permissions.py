from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class OrgPermissions(ModelPermissions):
    model = "organisation"

    # ADD = P("organisation.add_organisation")  # FIXME: We don't know about the context
    CHANGE = P("organisation.change_organisation")
    DELETE = P("organisation.delete_organisation")
    VIEW = P("organisation.view_organisation")
    MANAGE = P("organisation.manage_organisation")


class TOSPermissions(ModelPermissions):
    model = "tos"

    ADD = P("organisation.add_termsofservice", context="organisation")
    CHANGE = P("organisation.change_termsofservice")
    DELETE = P("organisation.delete_termsofservice")
    VIEW = P("organisation.view_termsofservice")


class UserConsentPermissions(ModelPermissions):
    model = "user_consent"

    ADD = P("organisation.add_userconsent", context="organisation")
    CHANGE = P("organisation.change_userconsent")
    DELETE = P("organisation.delete_userconsent")
    VIEW = P("organisation.view_userconsent")
