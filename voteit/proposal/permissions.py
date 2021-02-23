from voteit.core.registries import permissions


class ProposalPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.proposal.models import Proposal
    >>> find_bad_permission_names(ProposalPermissions, Proposal)

    """

    ADD = permissions.create("proposal.add_proposal", "agenda.AgendaItem")
    CHANGE = permissions.create("proposal.change_proposal", "proposal.Proposal")
    DELETE = permissions.create("proposal.delete_proposal", "proposal.Proposal")
    VIEW = permissions.create("proposal.view_proposal", "proposal.Proposal")
    RETRACT = permissions.create("proposal.retract_proposal", "proposal.Proposal")
