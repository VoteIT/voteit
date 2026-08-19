from __future__ import annotations

from voteit.messaging.base import AddedOrUpdatedSchema
from voteit.messaging.decorators import outgoing
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted


class ProposalAddedOrUpdatedSchema(AddedOrUpdatedSchema):
    created: str
    modified: str | None = None


@outgoing
class ProposalAdded(BaseObjectAdded):
    name = "proposal.added"
    schema = ProposalAddedOrUpdatedSchema
    data: ProposalAddedOrUpdatedSchema


@outgoing
class ProposalChanged(BaseObjectChanged):
    name = "proposal.changed"
    schema = ProposalAddedOrUpdatedSchema
    data: ProposalAddedOrUpdatedSchema


@outgoing
class ProposalDeleted(BaseObjectDeleted):
    name = "proposal.deleted"


@outgoing
class TextDocumentAdded(BaseObjectAdded):
    name = "text_document.added"


@outgoing
class TextDocumentChanged(BaseObjectChanged):
    name = "text_document.changed"


@outgoing
class TextDocumentDeleted(BaseObjectDeleted):
    name = "text_document.deleted"
