models_to_register = set()  # Temp registration, will be deleted

RQ_DEFAULT_QUEUE = "default"
RQ_LONG_QUEUE = "long"


class PERM:
    """
    Common base permission names. Use together with rules
    """

    VIEW = "view"
    ADD = "add"
    CHANGE = "change"
    DELETE = "delete"
    HANDLE = "handle"
    CHANGE_ROLES = "change_roles"
    VIEW_ROLES = "view_roles"
