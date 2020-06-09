from django.utils.translation import gettext as _


class MotionProcessWf:
    PRIVATE = "private"
    OPEN = "open"
    CLOSED = "closed"

    states = {
        PRIVATE: _("Private"),
        OPEN: _("Open"),
        CLOSED: _("Closed"),
    }
    initial = PRIVATE

    @classmethod
    def choices(cls):
        return cls.states.items()


class MotionWf:
    DRAFT = "draft"
    PUBLISHED = "published"
    RETRACTED = "retracted"
    ACCEPTED = "accepted"
    UNHANDLED = "unhandled"

    states = {
        DRAFT: _("Draft"),
        PUBLISHED: _("Published"),
        RETRACTED: _("Retracted"),
        ACCEPTED: _("Accepted"),
        UNHANDLED: _("Unhandled"),
    }
    initial = DRAFT

    @classmethod
    def choices(cls):
        return cls.states.items()
