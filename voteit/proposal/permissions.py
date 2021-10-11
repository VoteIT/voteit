from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class ProposalPermissions(ModelPermissions):
    model = "proposal"
    ADD = P("proposal.add_proposal", context="agenda_item")
    CHANGE = P("proposal.change_proposal")
    DELETE = P("proposal.delete_proposal")
    VIEW = P("proposal.view_proposal")
    RETRACT = P("proposal.retract_proposal")


class TextDocumentPermissions(ModelPermissions):
    model = "text_document"
    ADD = P("proposal.add_textdocument", context="agenda_item")
    CHANGE = P("proposal.change_textdocument")
    DELETE = P("proposal.delete_textdocument")
    VIEW = P("proposal.view_textdocument")


# class DiffProposalPermissions(ModelPermissions):
#     model = "diff_proposal"
#     ADD = P("proposal.add_proposal", context="agenda_item")
#     CHANGE = P("proposal.change_proposal")
#     DELETE = P("proposal.delete_proposal")
#     VIEW = P("proposal.view_proposal")
#     RETRACT = P("proposal.retract_proposal")
