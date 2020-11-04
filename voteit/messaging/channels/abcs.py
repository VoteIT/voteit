from __future__ import annotations

from abc import ABC, abstractmethod
from logging import getLogger
from typing import Optional, TYPE_CHECKING

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Model

from voteit.messaging.messages.abcs import AbstractTransmittableMessage

if TYPE_CHECKING:
    from channels_redis.core import RedisChannelLayer
    from voteit.messaging.consumers import WebsocketDemuxConsumer


logger = getLogger(__name__)


class AbstractChannel(ABC):
    """ Classic publish/subscribe pattern. This represents a channel that a consumer (websocket connection)
        can subscribe to.
    """
    logger = logger
    channel_layer:RedisChannelLayer  # FIXME?
    consumer_channel:Optional[str]

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """ Return name of this channel, probably based on the primary key of an object"""
        pass

    def __init__(self, consumer_channel:Optional[str]=None, channel_layer:Optional[RedisChannelLayer]=None):
        self.channel_layer = channel_layer and channel_layer or get_channel_layer()
        self.consumer_channel = consumer_channel

    @classmethod
    def from_consumer(cls, consumer: WebsocketDemuxConsumer, channel_name=None):
        return cls(consumer_channel=consumer.channel_name, channel_layer=consumer.channel_layer)

    async def subscribe(self, message_id=None, **kwargs):
        assert self.consumer_channel
        self.logger.debug(
            "Subscribed to %s",
            self.channel_name,
        )
        await self.channel_layer.group_add(
            self.channel_name, self.consumer_channel
        )

    def sync_subscribe(self, message_id=None, **kwargs):
        async_to_sync(self.subscribe)(message_id=message_id, **kwargs)

    async def publish(self, message: AbstractTransmittableMessage, message_id=None, **kwargs):
        self.logger.debug(
            "Published to %s",
            self.channel_name,
        )
        assert isinstance(message, AbstractTransmittableMessage)
        payload = message.format_payload(message_id)
        await self.channel_layer.group_send(self.channel_name, payload)

    def sync_publish(self, message: AbstractTransmittableMessage, message_id=None, **kwargs):
        async_to_sync(self.publish)(message, message_id=message_id, **kwargs)

    async def leave(self, message_id=None, **kwargs):
        assert self.consumer_channel
        self.logger.debug(
            "Left %s",
            self.channel_name,
        )
        await self.channel_layer.group_discard(
            self.channel_name, self.consumer_channel
        )

    def sync_leave(self, message_id=None, **kwargs):
        async_to_sync(self.leave)(message_id=message_id, **kwargs)


class AbstractObjectChannel(AbstractChannel):
    """ A channel that has to do with a specific object. For instance, the agenda channel is related to a meeting.
    """
    logger = logger
    pk: int  # Primary key of the object that this channel is about
    instance = None

    def __init__(self, pk:int, consumer_channel:Optional[str]=None, channel_layer:Optional[RedisChannelLayer]=None):
        self.pk = pk
        super(AbstractObjectChannel, self).__init__(consumer_channel, channel_layer)

    @property
    @abstractmethod
    def Model(self) -> Model:
        """ Set as property on subclass. Model should be the type of model this object channel is for."""
        pass

    @classmethod
    def from_pk(cls, pk:int, consumer_channel:Optional[str]=None) -> AbstractObjectChannel:
        return cls(pk, consumer_channel)

    @classmethod
    def from_instance(cls, instance:Model, consumer_channel:Optional[str]=None) -> AbstractObjectChannel:
        assert isinstance(instance, cls.Model), f"Instance must be a {cls.Model}"
        inst = cls.from_pk(instance.pk, consumer_channel)
        inst.instance = instance
        return inst

    def get_instance(self) -> Model:
        if self.instance is None:
            self.instance = self.Model.objects.get(pk=self.pk)
        return self.instance

    @abstractmethod
    def allow_subscribe(self, user):
        """ Override and call this before subscribing. Due to sync/async and the complexity of
            permissions this won't be enforced before calling subscribe.

            This must be implemented, since subscribe can be called by anyone.
        """
        pass

    def allow_publish(self, user):
        """ Override and call this before publishing. Due to sync/async and the complexity of
            permissions this won't be enforced before calling publish.

            Defaulting to false is ok here
        """
        return False

    def allow_leave(self, user):
        """ Override and call this before leaving. Due to sync/async and the complexity of
            permissions this won't be enforced before calling leave.

            Leave shouldn't require the same permission checks so we'll settle on allowing this as default.
        """
        return True
