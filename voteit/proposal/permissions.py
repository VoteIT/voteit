from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class ProposalPermissions(ModelPermissions):
    model = "proposal"
    ADD = P("proposal.add_proposal", context="agenda_item")
    CHANGE = P("proposal.change_proposal")
    DELETE = P("proposal.delete_proposal")
    VIEW = P("proposal.view_proposal")
    RETRACT = P("proposal.retract_proposal")
