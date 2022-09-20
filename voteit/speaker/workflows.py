from django.utils.translation import gettext as _


class SpeakerListWf:
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


class SpeakerSystemWf:
    INACTIVE = "inactive"
    ACTIVE = "active"
    ARCHIVED = "archived"
    states = {
        INACTIVE: _("Inactive"),
        ACTIVE: _("Active"),
        ARCHIVED: _("Archived"),
    }
    initial = ACTIVE

    @classmethod
    def choices(cls):
        return cls.states.items()
