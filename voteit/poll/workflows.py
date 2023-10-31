from django.utils.translation import gettext as _


class PollWf:
    PRIVATE = "private"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    FINISHED = "finished"
    WITHHELD = "withheld"
    CANCELED = "canceled"
    FAILED = "failed"
    NO_RESULT = "no_result"
    states = {
        PRIVATE: _("Private"),
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        FINISHED: _("Finished"),
        WITHHELD: _("Withheld"),
        CANCELED: _("Canceled"),
        FAILED: _("Failed"),
        NO_RESULT: _("No result"),
    }
    initial = PRIVATE
    permissive_states = {PRIVATE, UPCOMING}  # States where moderators can do changes
    finished_states = {FINISHED, WITHHELD}

    @classmethod
    def choices(cls):
        return cls.states.items()
