from django.utils.translation import gettext as _


class MeetingWf:
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    ARCHIVING = "archiving"
    ARCHIVED = "archived"
    states = {
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        ARCHIVING: _("Archiving"),
        ARCHIVED: _("Archived"),
    }
    initial = UPCOMING

    @classmethod
    def choices(cls):
        return cls.states.items()
