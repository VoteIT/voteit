from django.utils.translation import gettext as _


class PresenceCheckWf:
    OPEN = "open"
    CLOSED = "closed"
    states = {
        OPEN: _("Open"),
        CLOSED: _("Closed"),
    }
    initial = OPEN

    @classmethod
    def choices(cls):
        return cls.states.items()
