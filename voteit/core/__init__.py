models_to_register = set()  # Temp registration, will be deleted

RQ_DEFAULT_QUEUE = "default"
RQ_LONG_QUEUE = "long"
NOT_ALLOWED_SM_GUARD = "not_allowed"


class PERM:
    """
    Common base permission names. Use together with rules
    """

    VIEW = "view"
    ADD = "add"
    CHANGE = "change"
    DELETE = "delete"
    MODERATE = "moderate"
    HANDLE = "handle"
    CHANGE_ROLES = "change_roles"
    VIEW_ROLES = "view_roles"
    CHANGE_STATE = "change_state"
    ARCHIVE = "archive"
    MANAGE = "manage"
    NOT_ALLOWED = "__not_allowed"
