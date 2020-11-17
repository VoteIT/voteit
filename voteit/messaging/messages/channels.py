from __future__ import annotations

from django.contrib.auth import get_user_model
from django_rq import job
from pydantic import validator
from typing import TYPE_CHECKING, Optional

from voteit.messaging.registries import websocket_incoming_messages
from voteit.messaging.registries import websocket_outgoing_messages
from voteit.messaging.utils import get_channel_registry
from voteit.messaging.messages.abcs import (
    AbstractIncomingMessage,
    AbstractOutgoingMessage,
)

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer

User = get_user_model()


SUBSCRIBE = "channel.subscribe"
LEAVE = "channel.leave"
OBJECT_SUBSCRIBE = "object.subscribe"
OBJECT_LEAVE = "object.leave"

SUBSCRIBED = "channel.subscribed"
LEFT = "channel.left"
OBJECT_SUBSCRIBED = "channel.subscribed"
OBJECT_LEFT = "channel.left"

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
        subscribe.delay(
            user_pk=consumer.user.pk,
            channel_type=self.channel_type,
            consumer_name=consumer.channel_name,
            pk=self.pk,
            message_id=message_id,
        )


@websocket_incoming_messages(OBJECT_LEAVE)
class ObjectLeave(BaseObjectChannelMessage):
    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        leave.delay(
            user_pk=consumer.user.pk,
            channel_type=self.channel_type,
            consumer_name=consumer.channel_name,
            pk=self.pk,
            message_id=message_id,
        )


# class BaseConsumerChannelMessage(AbstractIncomingMessage):
#     channel_type: str  # This is the channel type, from the internal channel_registry
#     channel_name: str  #
#
#     @validator("channel_type")
#     def real_channel_type(cls, v):
#         return _check_channel_type(v)


# @websocket_incoming_messages(SUBSCRIBE)
# class Subscribe(BaseConsumerChannelMessage):
#
#     async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
#         cr = get_channel_registry()
#         channel = cr[self.channel_type](consumer, self.channel_name)
#         await channel.subscribe(message_id=message_id)
#
#
# @websocket_incoming_messages(LEAVE)
# class Leave(BaseConsumerChannelMessage):
#
#     async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
#         cr = get_channel_registry()
#         channel = cr[self.channel_type](consumer, self.channel_name)
#         await channel.leave(message_id=message_id)


# @websocket_outgoing_messages(SUBSCRIBED)
@websocket_outgoing_messages(OBJECT_SUBSCRIBED)
class Subscribed(AbstractOutgoingMessage):
    """ Confirm user subscribed"""


# @websocket_outgoing_messages(LEFT)
@websocket_outgoing_messages(OBJECT_LEFT)
class Left(AbstractOutgoingMessage):
    """ Confirm that user has left"""


def _get_user(pk):
    return User.objects.filter(pk=pk).first()


@job("default", timeout=500)
def subscribe(user_pk: int, channel_type: str, consumer_name: str, pk: int, message_id:Optional[int]=None):
    user = _get_user(user_pk)
    cr = get_channel_registry()
    channel_model = cr[channel_type]  # Should be validated already
    try:
        channel = channel_model.from_pk(pk, consumer_channel=consumer_name)
    except:
        #  FIXME Catch and send fail message
        raise
    if channel.allow_subscribe(user):
        channel.sync_subscribe(message_id=message_id)
        msg = Subscribed()
        msg.send(consumer_name, message_id=message_id, success=True)
    else:
        pass
        # FIXME: Send permission error


@job("default", timeout=5)
def leave(user_pk: int, channel_type: str, consumer_name: str, pk: int, message_id:Optional[int]=None):
    user = _get_user(user_pk)
    cr = get_channel_registry()
    channel_model = cr[channel_type]  # Should be validated already
    try:
        channel = channel_model.from_pk(pk, consumer_channel=consumer_name)
    except:
        #  FIXME Catch and send fail message
        raise
    if channel.allow_leave(user):
        channel.sync_leave(message_id=message_id)
        msg = Left()
        msg.send(consumer_name, message_id=message_id, success=True)
    else:
        pass
        # FIXME: Send permission error
