from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import meeting_components


@meeting_components
class ProposalPrint(ComponentAdapter):
    name = "proposal_print"
    title = "Proposal print"
    multiple = False
