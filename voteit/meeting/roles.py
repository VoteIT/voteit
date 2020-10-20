from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role, roles
from voteit.meeting.models import Meeting
from voteit.meeting.rules import is_participant
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_potential_voter
from voteit.meeting.rules import is_discusser
from voteit.meeting.rules import is_proposer


__all__ = ("Participant", "Moderator", "PotentialVoter", "Discusser", "Proposer")


@roles
class Participant(Role):
    """ Someone who can view a meeting.
    """

    model = Meeting
    m2m_field = "participants"
    title = _("Meeting participant")
    name = "participant"


@roles
class Moderator(Role):
    model = Meeting
    m2m_field = "moderators"
    title = _("Meeting moderator")
    name = "moderator"


Moderator.add_requirement(Participant)


@roles
class PotentialVoter(Role):
    model = Meeting
    m2m_field = "potential_voters"
    title = _("Potential voter")
    name = "potential_voter"


PotentialVoter.add_requirement(Participant)


@roles
class Discusser(Role):
    model = Meeting
    m2m_field = "discussers"
    title = _("Discusser")
    name = "discusser"


Discusser.add_requirement(Participant)


@roles
class Proposer(Role):
    model = Meeting
    m2m_field = "proposers"
    title = _("Proposer")
    name = "proposer"


Proposer.add_requirement(Participant)
