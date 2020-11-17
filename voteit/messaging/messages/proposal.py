from voteit.messaging.messages.abcs import AbstractOutgoingMessage
from voteit.messaging.registries import websocket_outgoing_messages

# FIXME: This is a stub

@websocket_outgoing_messages("proposal.changed")
class ProposalUpdated(AbstractOutgoingMessage):
    items: list


@websocket_outgoing_messages("proposal.deleted")
class ProposalDeleted(AbstractOutgoingMessage):
    items: list
