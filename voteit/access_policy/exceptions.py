from django.utils.translation import gettext_lazy as _


class InviteError(Exception):
    message = _("Invites caused an error")

    def __init__(self, message: str = None):
        if message is not None:
            self.message = message
        super().__init__(self.message)
