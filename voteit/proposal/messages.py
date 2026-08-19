from __future__ import annotations

from typing import Literal

from voteit.messaging.base import AddedOrUpdatedSchema
from voteit.messaging.decorators import outgoing
from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted


class ProposalAddedOrUpdatedSchema(AddedOrUpdatedSchema):
    created: str
    modified: str | None = None


@outgoing
class ProposalChanged(ObjectAddedOrChanged):
    action: Literal["proposal.changed"] = "proposal.changed"


@outgoing
class ProposalDeleted(ObjectDeleted):
    action: Literal["proposal.deleted"] = "proposal.deleted"


@outgoing
class TextDocumentChanged(ObjectAddedOrChanged):
    action: Literal["text_document.changed"] = "text_document.changed"


@outgoing
class TextDocumentDeleted(ObjectDeleted):
    action: Literal["text_document.deleted"] = "text_document.deleted"
