from voteit.core.component import Registry
from voteit.messaging.abcs import AbstractChannel
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage

incoming_messages = Registry(BaseIncomingMessage)
outgoing_messages = Registry(BaseOutgoingMessage)
channel_registry = Registry(AbstractChannel)
