from django.utils.translation import gettext as _


class MotionProcessWf:
    OPEN = "open"
    CLOSED = "closed"

    states = {
        OPEN: _("Open"),
        CLOSED: _("Closed"),
    }
    initial = OPEN

    @classmethod
    def choices(cls):
        return cls.states.items()


class MotionWf:
    DRAFT = "draft"
    PUBLISHED = "published"
    RETRACTED = "retracted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNHANDLED = "unhandled"

    states = {
        DRAFT: _("Draft"),
        PUBLISHED: _("Published"),
        RETRACTED: _("Retracted"),
        ACCEPTED: _("Accepted"),
        REJECTED: _("Rejected"),
        UNHANDLED: _("Unhandled"),
    }
    initial = DRAFT

    @classmethod
    def choices(cls):
        return cls.states.items()
