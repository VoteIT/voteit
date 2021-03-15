from __future__ import annotations

from typing import TYPE_CHECKING

# from django.contrib.auth import get_user_model

from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted

# User = get_user_model()


if TYPE_CHECKING:
    pass


# @incoming
# class AddProposal(BaseAddObject):
#     name = "proposal.add"
#     permission = ProposalPermissions.ADD
#     model = AgendaItem  # This is the context for the action!
#     add_model = Proposal
#     relation_queryset_attribute = "proposals"
#
#
# @incoming
# class ChangeProposal(BaseChangeObject):
#     name = "proposal.change"
#     model = Proposal
#     permission = ProposalPermissions.CHANGE
#
#
# @incoming
# class DeleteProposal(BaseDeleteObject):
#     name = "proposal.delete"
#     model = Proposal
#     permission = ProposalPermissions.DELETE


@outgoing
class ProposalAdded(BaseObjectAdded):
    name = "proposal.added"


@outgoing
class ProposalChanged(BaseObjectChanged):
    name = "proposal.changed"


@outgoing
class ProposalDeleted(BaseObjectDeleted):
    name = "proposal.deleted"
