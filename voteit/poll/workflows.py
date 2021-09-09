from django.utils.translation import gettext as _


class PollWf:
    PRIVATE = "private"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    FINISHED = "finished"
    CANCELED = "canceled"
    FAILED = "failed"
    states = {
        PRIVATE: _("Private"),
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        FINISHED: _("Finished"),
        CANCELED: _("Canceled"),
        FAILED: _("Failed"),
    }
    initial = PRIVATE
    permissive_states = {PRIVATE, UPCOMING}  # States where moderators can do changes

    @classmethod
    def choices(cls):
        return cls.states.items()
