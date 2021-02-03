from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from voteit.agenda.models import AgendaItem

from voteit.messaging.decorators import outgoing, incoming
from voteit.messaging.messages.base import (
    BaseObjectAdded,
    BaseObjectChanged,
    BaseObjectDeleted,
    BaseAddObject,
    BaseChangeObject,
    BaseDeleteObject,
)
from voteit.proposal.models import Proposal
from voteit.proposal.permissions import ProposalPermissions

User = get_user_model()


if TYPE_CHECKING:
    pass


@incoming
class AddProposal(BaseAddObject):
    name = "proposal.add"
    permission = ProposalPermissions.ADD
    model = AgendaItem  # This is the context for the action!
    add_model = Proposal
    relation_queryset_attribute = "proposals"


@incoming
class ChangeProposal(BaseChangeObject):
    name = "proposal.change"
    model = Proposal
    permission = ProposalPermissions.CHANGE


@incoming
class DeleteProposal(BaseDeleteObject):
    name = "proposal.delete"
    model = Proposal
    permission = ProposalPermissions.DELETE


@outgoing
class ProposalAdded(BaseObjectAdded):
    name = "proposal.added"


@outgoing
class ProposalChanged(BaseObjectChanged):
    name = "proposal.changed"


@outgoing
class ProposalDeleted(BaseObjectDeleted):
    name = "proposal.deleted"
