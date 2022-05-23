from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


# FIXME: There's a quirk with how REST framework viewset handles permissions with subclassed objects that
# exist in the database. (At least due to how we've done it)
# So some operations will be on DiffProposal and some will be on the parent Proposal object.
# So diff_proposal must be a valid context for the proposal permissions too
class ProposalPermissions(ModelPermissions):
    model = "proposal"
    ADD = P("proposal.add_proposal", context="agenda_item")
    CHANGE = P("proposal.change_proposal", context={"proposal", "diff_proposal"})
    DELETE = P("proposal.delete_proposal", context={"proposal", "diff_proposal"})
    VIEW = P("proposal.view_proposal", context={"proposal", "diff_proposal"})
    RETRACT = P("proposal.retract_proposal", context={"proposal", "diff_proposal"})


class DiffProposalPermissions(ModelPermissions):
    model = "diff_proposal"
    ADD = P("proposal.add_diffproposal", context="agenda_item")
    CHANGE = P("proposal.change_diffproposal")
    DELETE = P("proposal.delete_diffproposal")
    VIEW = P("proposal.view_diffproposal")
    RETRACT = P("proposal.retract_diffproposal")


class TextDocumentPermissions(ModelPermissions):
    model = "text_document"
    ADD = P("proposal.add_textdocument", context="agenda_item")
    CHANGE = P("proposal.change_textdocument")
    DELETE = P("proposal.delete_textdocument")
    VIEW = P("proposal.view_textdocument")
