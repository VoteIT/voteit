from __future__ import annotations

from typing import TYPE_CHECKING

from channels.auth import logout
from pydantic.main import BaseModel

from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.channels.user import UserChannel
from voteit.messaging.decorators import incoming, outgoing
from voteit.messaging.models import Connection
from voteit.messaging.utils import cleanup_connection_status

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


@incoming
class LogoutCommand(AsyncRunnable):
    name = "user.logout"

    async def run(self, consumer: WebsocketDemuxConsumer):
        channel = UserChannel.from_instance(consumer.user, consumer.channel_name)
        msg = LogoutConnection.from_message(self)
        await channel.async_publish(msg)


@incoming
class LogoutConnection(AsyncRunnable):
    name = "user.connection"

    async def run(self, consumer: WebsocketDemuxConsumer):
        print("Got logout command")
        await logout(consumer.scope)
        # reset user?
        await consumer.close(1000)


@incoming
class ConnectionCount(DeferredJob):
    name = "user.connection_count"

    def run_job(self):
        cleanup_connection_status(only_user=self.user)
        count = Connection.objects.filter(user=self.user, online=True).count()
        msg = ConnectionsCounted.from_message(self, connections=count)
        msg.send_outgoing(self.mm.consumer_name, success=True)


class ConnectionsCountedSchema(BaseModel):
    connections: int


@outgoing
class ConnectionsCounted(BaseOutgoingMessage):
    name = "user.connections_counted"
    schema = ConnectionsCountedSchema
    data: ConnectionsCountedSchema


# @websocket_incoming_messages("user.connection_count")
# class ConnectionCount(AbstractIncomingMessage):
#     # Note: This doesn't give an accurate count since consumer hashes stay in groups for all abnormal disconnects.
#     async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
#         channel = UserChannel.from_instance(consumer.user)
#         group = channel.channel_name
#         group_key = consumer.channel_layer._group_key(group)
#         async with consumer.channel_layer.connection(
#             consumer.channel_layer.consistent_hash(group)
#         ) as connection:
#             count = await connection.zcount(group_key)
#         msg = ConnectionsCounted(active=count)
#         await channel.publish(msg, message_id=message_id)
