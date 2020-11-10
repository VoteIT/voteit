from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import validator

from voteit.messaging.registries import websocket_incoming_messages, websocket_outgoing_messages
from voteit.messaging.messages.abcs import AbstractIncomingMessage, AbstractOutgoingMessage

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


@websocket_incoming_messages("schema.get")
class GetSchema(AbstractIncomingMessage):
    """ Request json_schema for a specific message type.
        Must be in websocket_incoming_messages registry.
    """
    message_type: str

    @validator("message_type")
    def check_message_type(cls, v):
        v = v.lower()
        if v not in websocket_incoming_messages:
            raise ValueError(f"'{v}' is not registered as an incoming message type")
        return v

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        msg_type = websocket_incoming_messages[self.message_type]
        msg = SendSchema(message_schema=msg_type.schema_json())
        await msg.async_send(consumer.channel_name, message_id=message_id)

    class Config:
        title = "Get schema"


@websocket_outgoing_messages("schema.send")
class SendSchema(AbstractOutgoingMessage):
    message_schema: str
