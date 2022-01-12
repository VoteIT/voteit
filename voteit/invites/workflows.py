from django.utils.translation import gettext_lazy as _


class InviteWf:
    OPEN = "open"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

    states = {
        OPEN: _("Open"),
        EXPIRED: _("Expired"),
        REVOKED: _("Revoked"),
        ACCEPTED: _("Accepted"),
        REJECTED: _("Rejected"),
    }
    initial = OPEN

    @classmethod
    def choices(cls):
        return cls.states.items()
