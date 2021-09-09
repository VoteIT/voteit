""" Common workflows. """
from django.utils.translation import gettext as _


class AcceptanceWf:
    UNHANDLED = "unhandled"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    states = {
        UNHANDLED: _("Unhandled"),
        ACCEPTED: _("Accepted"),
        REJECTED: _("Rejected"),
    }
    initial = UNHANDLED

    @classmethod
    def choices(cls):
        return cls.states.items()


class UserWf:
    INCOMPLETE = "incomplete"
    ACTIVE = "active"
    # BANNED = "banned"
    # REMOVED?
    states = {
        INCOMPLETE: _("Incomplete"),
        ACTIVE: _("Active"),
    }
    initial = INCOMPLETE

    @classmethod
    def choices(cls):
        return cls.states.items()
