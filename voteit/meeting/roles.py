from django.utils.translation import gettext as _

from voteit.core.role import Role

from voteit.meeting.models import MeetingRoles

__all__ = (
    "ROLE_PARTICIPANT",
    "ROLE_MODERATOR",
    "ROLE_POTENTIAL_VOTER",
    "ROLE_DISCUSSER",
    "ROLE_PROPOSER",
)

ROLE_PARTICIPANT = Role("participant", title=_("Participant"))
ROLE_MODERATOR = Role("moderator", title=_("Moderator"))
ROLE_POTENTIAL_VOTER = Role("potential_voter", title=_("Potential voter"))
ROLE_DISCUSSER = Role("discusser", title=_("Discusser"))
ROLE_PROPOSER = Role("proposer", title=_("Proposer"))

MeetingRoles.add_valid(
    ROLE_PARTICIPANT,
    ROLE_MODERATOR,
    ROLE_POTENTIAL_VOTER,
    ROLE_DISCUSSER,
    ROLE_PROPOSER,
)


ROLE_MODERATOR.add_requirement(ROLE_PARTICIPANT)
ROLE_POTENTIAL_VOTER.add_requirement(ROLE_PARTICIPANT)
ROLE_DISCUSSER.add_requirement(ROLE_PARTICIPANT)
ROLE_PROPOSER.add_requirement(ROLE_PARTICIPANT)
