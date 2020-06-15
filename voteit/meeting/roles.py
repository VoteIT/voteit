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

    rule = is_participant
    model = Meeting
    m2m_field = "participants"
    title = _("Meeting participant")
    name = "participant"


@roles
class Moderator(Role):
    rule = is_moderator
    model = Meeting
    m2m_field = "moderators"
    title = _("Meeting moderator")
    name = "moderator"


Moderator.add_requirement(Participant)


@roles
class PotentialVoter(Role):
    rule = is_potential_voter
    model = Meeting
    m2m_field = "potential_voters"
    title = _("Potential voter")
    name = "potential_voter"


PotentialVoter.add_requirement(Participant)


@roles
class Discusser(Role):
    rule = is_discusser
    model = Meeting
    m2m_field = "discussers"
    title = _("Discusser")
    name = "discusser"


Discusser.add_requirement(Participant)


@roles
class Proposer(Role):
    rule = is_proposer
    model = Meeting
    m2m_field = "proposers"
    title = _("Proposer")
    name = "proposer"


Proposer.add_requirement(Participant)
