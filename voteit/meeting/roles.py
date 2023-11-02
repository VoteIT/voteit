from django.utils.translation import gettext as _

from voteit.core.role import Role


__all__ = (
    "ROLE_PARTICIPANT",
    "ROLE_MODERATOR",
    "ROLE_POTENTIAL_VOTER",
    "ROLE_DISCUSSER",
    "ROLE_PROPOSER",
)

ROLE_PARTICIPANT = Role("pa", title=_("Participant"))
ROLE_MODERATOR = Role("mo", title=_("Moderator"))
ROLE_POTENTIAL_VOTER = Role("pv", title=_("Potential voter"))
ROLE_DISCUSSER = Role("di", title=_("Discusser"))
ROLE_PROPOSER = Role("pr", title=_("Proposer"))

ROLE_MODERATOR.add_requirement(ROLE_PARTICIPANT)
ROLE_POTENTIAL_VOTER.add_requirement(ROLE_PARTICIPANT)
ROLE_DISCUSSER.add_requirement(ROLE_PARTICIPANT)
ROLE_PROPOSER.add_requirement(ROLE_PARTICIPANT)
