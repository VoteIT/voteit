from django.utils.translation import gettext as _


class InviteWf:
    OPEN = "open"
    # PROCESSING = "processing"
    # FAILED = "failed"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

    states = {
        OPEN: _("Open"),
        # PROCESSING: _("Processing"),
        # FAILED: _("Failed"),
        EXPIRED: _("Expired"),
        REVOKED: _("Revoked"),
        ACCEPTED: _("Accepted"),
        REJECTED: _("Rejected"),
    }
    initial = OPEN

    @classmethod
    def choices(cls):
        return cls.states.items()
