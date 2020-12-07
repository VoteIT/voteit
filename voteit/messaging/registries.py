from voteit.core.component import Registry
from voteit.messaging.abcs import BaseIncomingMessage, BaseOutgoingMessage
from voteit.messaging.channels.abcs import AbstractChannel

incoming_messages = Registry(BaseIncomingMessage)
outgoing_messages = Registry(BaseOutgoingMessage)

# Channel registry
channel_registry = Registry(AbstractChannel)
