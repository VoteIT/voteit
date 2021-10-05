from __future__ import annotations

from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted


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
class TextParagraphAdded(BaseObjectAdded):
    name = "text_paragraph.added"


@outgoing
class TextParagraphChanged(BaseObjectChanged):
    name = "text_paragraph.changed"


@outgoing
class TextParagraphDeleted(BaseObjectDeleted):
    name = "text_paragraph.deleted"
