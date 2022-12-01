from django.utils.translation import gettext as _


class MeetingWf:
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    ARCHIVING = "archiving"
    ARCHIVED = "archived"
    DELETING = "deleting"
    states = {
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        ARCHIVING: _("Archiving"),
        ARCHIVED: _("Archived"),
        DELETING: _("Deleting"),
    }
    initial = UPCOMING

    @classmethod
    def choices(cls):
        return cls.states.items()

    finished_states = {CLOSED, ARCHIVING, ARCHIVED, DELETING}
    archived_states = {ARCHIVING, ARCHIVED, DELETING}
