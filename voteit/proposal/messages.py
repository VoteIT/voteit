from __future__ import annotations

from voteit.messaging.decorators import outgoing
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted


@outgoing
class ProposalAdded(BaseObjectAdded):
    name = "proposal.added"


@outgoing
class ProposalChanged(BaseObjectChanged):
    name = "proposal.changed"


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
