from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


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
