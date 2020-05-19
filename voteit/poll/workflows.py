from django.utils.translation import gettext as _


class PollWf:
    PRIVATE = "private"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    CANCELED = "canceled"
    FAILED = 'failed'
    states = {
        PRIVATE: _("Private"),
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        CANCELED: _("Canceled"),
        FAILED: _('Failed')
    }
    initial = PRIVATE

    @classmethod
    def choices(cls):
        return cls.states.items()
