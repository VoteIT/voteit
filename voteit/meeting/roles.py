from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role
# from voteit.meeting.models import Meeting
# from voteit.meeting.rules import is_participant
# from voteit.meeting.rules import is_moderator
# from voteit.meeting.rules import is_potential_voter
# from voteit.meeting.rules import is_discusser
# from voteit.meeting.rules import is_proposer

from voteit.meeting.models import MeetingRoles

__all__ = ("ROLE_PARTICIPANT", "ROLE_MODERATOR", "ROLE_POTENTIAL_VOTER", "ROLE_DISCUSSER", "ROLE_PROPOSER")

ROLE_PARTICIPANT = Role("participant")
ROLE_MODERATOR = Role("moderator")
ROLE_POTENTIAL_VOTER = Role("potential_voter")
ROLE_DISCUSSER = Role("discusser")
ROLE_PROPOSER = Role("proposer")

MeetingRoles.add_valid(
    ROLE_PARTICIPANT,
    ROLE_MODERATOR,
    ROLE_POTENTIAL_VOTER,
    ROLE_DISCUSSER,
    ROLE_PROPOSER
)


ROLE_MODERATOR.add_requirement(ROLE_PARTICIPANT)
ROLE_POTENTIAL_VOTER.add_requirement(ROLE_PARTICIPANT)
ROLE_DISCUSSER.add_requirement(ROLE_PARTICIPANT)
ROLE_PROPOSER.add_requirement(ROLE_PARTICIPANT)


# @roles
# class Participant(Role):
#     """ Someone who can view a meeting.
#     """
#
#     model = Meeting
#     m2m_field = "participants"
#     title = _("Meeting participant")
#     name = "participant"
#
#
# @roles
# class Moderator(Role):
#     model = Meeting
#     m2m_field = "moderators"
#     title = _("Meeting moderator")
#     name = "moderator"
#
#
# Moderator.add_requirement(Participant)
#
#
# @roles
# class PotentialVoter(Role):
#     model = Meeting
#     m2m_field = "potential_voters"
#     title = _("Potential voter")
#     name = "potential_voter"
#
#
# PotentialVoter.add_requirement(Participant)
#
#
# @roles
# class Discusser(Role):
#     model = Meeting
#     m2m_field = "discussers"
#     title = _("Discusser")
#     name = "discusser"
#
#
# Discusser.add_requirement(Participant)
#
#
# @roles
# class Proposer(Role):
#     model = Meeting
#     m2m_field = "proposers"
#     title = _("Proposer")
#     name = "proposer"
#
#
# Proposer.add_requirement(Participant)
