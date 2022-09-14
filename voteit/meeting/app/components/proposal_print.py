from voteit.meeting.abcs import MeetingComponentAdapter
from voteit.meeting.registries import meeting_components


@meeting_components
class ProposalPrint(MeetingComponentAdapter):
    name = "proposal_print"
    title = "Proposal print"
    multiple = False
