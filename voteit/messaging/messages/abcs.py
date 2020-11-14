from __future__ import annotations

from abc import ABC, abstractmethod
from logging import getLogger
from typing import TYPE_CHECKING, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from pydantic import BaseModel

from voteit.messaging.messages import OutgoingPayload
from voteit.messaging.messages import WEBSOCKET_OUTGOING_NAME
from voteit.messaging.messages import INTERNAL_MESSAGE

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


logger = getLogger(__name__)


class AbstractMessage(BaseModel, ABC):
    """ Any kind of message being passed through channels/websockets
    """

    pass


class AbstractConsumableMessage(AbstractMessage):
    """ A message that's meant to be consumed when it's deserialized.
    """

    @abstractmethod
    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        pass


class AbstractTransmittableMessage(AbstractMessage):
    """ A message that's meant to be serialized and transmitted somewhere.
        Note the difference in sync and async methods.
    """

    @abstractmethod
    def format_payload(self, message_id: Optional[str], state=""):
        pass

    async def async_send(
        self, channel: str, message_id: Optional[str] = None, state=""
    ):
        payload = self.format_payload(message_id, state=state)
        channel_layer = get_channel_layer()
        await channel_layer.send(channel, payload)

    async def async_group_send(
        self, channel: str, message_id: Optional[str] = None, state: str = ""
    ):
        payload = self.format_payload(message_id, state=state)
        channel_layer = get_channel_layer()
        print("Async sending to: ", channel)
        await channel_layer.group_send(channel, payload)

    def send(self, channel: str, message_id: Optional[str] = None, state: str = ""):
        payload = self.format_payload(message_id, state=state)
        channel_layer = get_channel_layer()
        print("Sending to: ", channel)
        async_to_sync(channel_layer.send)(channel, payload)

    def group_send(
        self, channel: str, message_id: Optional[str] = None, state: str = ""
    ):
        payload = self.format_payload(message_id, state=state)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(channel, payload)


class AbstractIncomingMessage(AbstractConsumableMessage):
    """ A message received from websocket. It's then consumed within the consumer context.
    """


class AbstractInternalMessage(AbstractConsumableMessage, AbstractTransmittableMessage):
    """ A message received internally from channels. It can be both transmittable and consumable.
        If this type of message is received via websocket, it will cause an error.
    """

    def format_payload(self, message_id: Optional[str], state: str = ""):
        from voteit.messaging.registries import internal_messages

        for (mtype, MessageType) in internal_messages.items():
            if self.__class__ == MessageType:
                return {
                    "type": INTERNAL_MESSAGE,
                    "p": self.json(),  # json?
                    "t": mtype,
                    "i": message_id,
                    "s": state,
                }
        raise KeyError(
            f"{self.__class__} not found in internal_messages registry, register the message type there first"
        )


class AbstractOutgoingMessage(AbstractTransmittableMessage):
    def format_payload(self, message_id: Optional[str], state: str = ""):
        from voteit.messaging.registries import websocket_outgoing_messages

        for (mtype, MessageType) in websocket_outgoing_messages.items():
            if self.__class__ == MessageType:
                payload = OutgoingPayload(p=self, t=mtype, i=message_id, s=state)
                return {"type": WEBSOCKET_OUTGOING_NAME, "payload": payload.json()}

        raise KeyError(
            f"{self.__class__} not found in websocket_outgoing_messages registry, register the message type there first"
        )
