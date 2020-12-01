from voteit.core.component import Registry
from voteit.messaging.abcs import BaseIncomingMessage, BaseOutgoingMessage
from voteit.messaging.channels.abcs import AbstractChannel
#from voteit.messaging.messages.abcs import AbstractIncomingMessage
#from voteit.messaging.messages.abcs import AbstractOutgoingMessage
#from voteit.messaging.messages.abcs import AbstractInternalMessage

# The different message types
#websocket_incoming_messages = Registry(AbstractIncomingMessage)
#websocket_outgoing_messages = Registry(AbstractOutgoingMessage)
#internal_messages = Registry(AbstractInternalMessage)

incoming_messages = Registry(BaseIncomingMessage)
outgoing_messages = Registry(BaseOutgoingMessage)

# Channel registry
channel_registry = Registry(AbstractChannel)
