from __future__ import annotations

from pydantic import validator
from typing import TYPE_CHECKING

from voteit.messaging.jobs import subscribe, leave
from voteit.messaging.registries import websocket_incoming_messages
from voteit.messaging.utils import get_channel_registry
from voteit.messaging.messages.abcs import AbstractIncomingMessage

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


SUBSCRIBE = "channel.subscribe"
LEAVE= "channel.leave"
OBJECT_SUBSCRIBE = "object.subscribe"
OBJECT_LEAVE = "object.leave"

# Probably not a generic publish message I'm guessing


def _check_channel_type(v: str):
    cr = get_channel_registry()
    v = v.lower()
    if v not in cr:
        raise ValueError(f"'{v}' is not a valid channel")
    return v


class BaseObjectChannelMessage(AbstractIncomingMessage):
    pk: int  # The pk of the model we need to fetch to check if user can subscribe
    channel_type: str  # This is the channel type, from the internal channel_registry

    @validator("channel_type")
    def real_channel_type(cls, v):
        return _check_channel_type(v)


@websocket_incoming_messages(OBJECT_SUBSCRIBE)
class ObjectSubscribe(BaseObjectChannelMessage):

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        subscribe.delay(user_pk=consumer.user.pk, channel_type=self.channel_type, consumer_name=consumer.channel_name, pk=self.pk, message_id=message_id)


@websocket_incoming_messages(OBJECT_LEAVE)
class ObjectLeave(BaseObjectChannelMessage):

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        leave.delay(user_pk=consumer.user.pk, channel_type=self.channel_type, consumer_name=consumer.channel_name, pk=self.pk, message_id=message_id)


class BaseConsumerChannelMessage(AbstractIncomingMessage):
    channel_type: str  # This is the channel type, from the internal channel_registry
    channel_name: str  #

    @validator("channel_type")
    def real_channel_type(cls, v):
        return _check_channel_type(v)


@websocket_incoming_messages(SUBSCRIBE)
class Subscribe(BaseConsumerChannelMessage):

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        cr = get_channel_registry()
        channel = cr[self.channel_type](consumer, self.channel_name)
        await channel.subscribe(message_id=message_id)


@websocket_incoming_messages(LEAVE)
class Leave(BaseConsumerChannelMessage):

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        cr = get_channel_registry()
        channel = cr[self.channel_type](consumer, self.channel_name)
        await channel.leave(message_id=message_id)
