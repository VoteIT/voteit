from django.utils.translation import gettext as _


class AgendaItemWf:
    PRIVATE = "private"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    states = {
        PRIVATE: _("Private"),
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
    }
    initial = PRIVATE

    @classmethod
    def choices(cls):
        return cls.states.items()
