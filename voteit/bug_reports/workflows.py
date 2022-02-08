from django.utils.translation import gettext as _


class BugReportWf:
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    IGNORED = "ignored"
    states = {
        UNRESOLVED: _("Unresolved"),
        RESOLVED: _("Resolved"),
        IGNORED: _("Ignored"),
    }
    initial = UNRESOLVED

    @classmethod
    def choices(cls):
        return cls.states.items()
