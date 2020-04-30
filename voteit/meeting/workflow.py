from django.utils.translation import gettext as _


class MeetingWf:
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    ARCHIVED = "archived"
    states = {
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        ARCHIVED: _("Archived"),
    }
    initial = UPCOMING

    @classmethod
    def choices(cls):
        return cls.states.items()
