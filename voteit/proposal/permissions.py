from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class ProposalPermissions(ModelPermissions):
    model = "proposal"
    ADD = P("proposal.add_proposal", context="agenda_item")
    # FIXME: We'll want to fetch context from subclassed objects instead,
    # much like the decorator receiver_all_subclasses work
    CHANGE = P("proposal.change_proposal", context={"proposal", "diff_proposal"})
    DELETE = P("proposal.delete_proposal", context={"proposal", "diff_proposal"})
    VIEW = P("proposal.view_proposal", context={"proposal", "diff_proposal"})
    RETRACT = P("proposal.retract_proposal", context={"proposal", "diff_proposal"})


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
