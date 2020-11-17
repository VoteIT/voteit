from voteit.messaging.messages.abcs import ObjectAdded, ObjectChanged, ObjectDeleted
from voteit.messaging.registries import websocket_outgoing_messages


@websocket_outgoing_messages("proposal.added")
class ProposalAdded(ObjectAdded):
    pass


@websocket_outgoing_messages("proposal.changed")
class ProposalChanged(ObjectChanged):
    pass


@websocket_outgoing_messages("proposal.deleted")
class ProposalDeleted(ObjectDeleted):
    pass
