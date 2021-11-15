from __future__ import annotations
from typing import TYPE_CHECKING

from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


@incoming
class IncomingPing(BaseIncomingMessage, AsyncRunnable):
    """
    User-initiated ping
    """

    name = "s.ping"

    async def run(self, consumer: WebsocketDemuxConsumer) -> OutgoingPong:
        response = OutgoingPong.from_message(self)
        await response.async_send_outgoing(consumer.channel_name, success=True)
        return response


@incoming
class IncomingPong(BaseIncomingMessage, AsyncRunnable):
    """
    Client response
    """

    name = "s.pong"

    async def run(self, consumer: WebsocketDemuxConsumer):
        # no action really
        pass


@outgoing
class OutgoingPing(BaseOutgoingMessage):
    """
    Server-initiated ping
    """

    name = "s.ping"


@outgoing
class OutgoingPong(BaseOutgoingMessage):
    """
    Response
    """

    name = "s.pong"
