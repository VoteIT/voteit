from django.utils.translation import gettext as _


class ProposalWf:
    PUBLISHED = "published"
    RETRACTED = "retracted"
    VOTING = "voting"
    APPROVED = "approved"
    DENIED = "denied"
    UNHANDLED = "unhandled"
    states = {
        PUBLISHED: _("Published"),
        RETRACTED: _("Retracted"),
        VOTING: _("Voting"),
        APPROVED: _("Approved"),
        DENIED: _("Denied"),
        UNHANDLED: _("Unhandled")
    }
    initial = PUBLISHED

    @classmethod
    def choices(cls):
        return cls.states.items()
