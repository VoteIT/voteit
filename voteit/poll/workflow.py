from django.utils.translation import gettext as _


class PollWf:
    PRIVATE = "private"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    CANCELED = "canceled"
    states = {
        PRIVATE: _("Private"),
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        CANCELED: _("Canceled"),
    }
    initial = PRIVATE

    @classmethod
    def choices(cls):
        return cls.states.items()
