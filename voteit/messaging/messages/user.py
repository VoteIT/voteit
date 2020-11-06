from __future__ import annotations

from typing import TYPE_CHECKING

from channels.auth import logout
from voteit.messaging.channels.user import UserChannel
from voteit.messaging.messages.abcs import (
    AbstractIncomingMessage,
    AbstractInternalMessage,
    AbstractOutgoingMessage,
)
from voteit.messaging.registries import internal_messages
from voteit.messaging.registries import (
    websocket_incoming_messages,
    websocket_outgoing_messages,
)

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


@websocket_incoming_messages("user.logout")
class LogoutAllConnections(AbstractIncomingMessage):
    """ Send logout command to all connected websockets. """

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        channel = UserChannel.from_instance(consumer.user)
        msg = LogoutCommand()
        await channel.publish(msg, message_id=message_id)


@internal_messages("user.logout")
class LogoutCommand(AbstractInternalMessage):
    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        print("Got logout command")
        await logout(consumer.scope)
        await consumer.close(1000)


@websocket_outgoing_messages("user.conenctions_counted")
class ConnectionsCounted(AbstractOutgoingMessage):
    active: int


@websocket_incoming_messages("user.connection_count")
class ConnectionCount(AbstractIncomingMessage):
    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        channel = UserChannel.from_instance(consumer.user)
        group = channel.channel_name
        group_key = consumer.channel_layer._group_key(group)
        async with consumer.channel_layer.connection(
            consumer.channel_layer.consistent_hash(group)
        ) as connection:
            count = await connection.zcount(group_key)
        msg = ConnectionsCounted(active=count)
        await channel.publish(msg, message_id=message_id)
