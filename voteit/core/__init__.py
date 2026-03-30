models_to_register = set()  # Temp registration, will be deleted

RQ_DEFAULT_QUEUE = "default"
RQ_LONG_QUEUE = "long"


class PERM:
    VIEW = "view"
    ADD = "add"
    CHANGE = "change"
    DELETE = "delete"
