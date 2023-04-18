from django.utils.translation import gettext_lazy as _


class InviteError(Exception):
    message = _("Invites caused an error")

    def __init__(self, message: str = None):
        if message is not None:
            self.message = message
        super().__init__(self.message)


class DataColValidationError(Exception):
    name: str
    index: int  # Start at 1
    rows: list[int]  # Start at 1
    message: str

    def __init__(self, *, name, index, rows, message="Invalid rows"):
        self.name = name
        self.index = index
        self.rows = rows
        self.message = message
        super().__init__()

    def __str__(self):
        return (
            f"Column {self.name} ({self.index}) validation failed at rows: {self.rows}"
        )
