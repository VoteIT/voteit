from django.utils.translation import gettext as _


class AgendaItemWf:
    PRIVATE = "private"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    ARCHIVED = "archived"
    states = {
        PRIVATE: _("Private"),
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        ARCHIVED: _("Archived"),
    }
    initial = PRIVATE

    @classmethod
    def choices(cls):
        return cls.states.items()

    finished_states = {CLOSED, ARCHIVED}
    archived_states = {ARCHIVED}
