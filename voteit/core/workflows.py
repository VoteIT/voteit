""" Common workflows. """
from django.utils.translation import gettext_lazy as _


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


class SendWf:
    CREATED = "created"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"

    states = {
        CREATED: _("Created"),
        SCHEDULED: _("Scheduled"),
        SENDING: _("Sending"),
        SENT: _("Sent"),
        FAILED: _("Failed"),
    }
    initial = CREATED

    @classmethod
    def choices(cls):
        return cls.states.items()


class EnabledWf:
    ON = "on"
    OFF = "off"
    states = {
        ON: _("On"),
        OFF: _("Off"),
    }
    initial = OFF

    @classmethod
    def choices(cls):
        return cls.states.items()
