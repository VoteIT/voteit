from __future__ import annotations

from typing import TYPE_CHECKING

from django.dispatch import receiver
from voteit.messaging.messages.abcs import AbstractIncomingMessage, AbstractOutgoingMessage
from voteit.messaging.registries import websocket_incoming_messages, websocket_outgoing_messages
from voteit.messaging.signals import client_connect

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


@websocket_incoming_messages("testing.hello")
class Hello(AbstractIncomingMessage):
    greeting: str = ""

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        greeting = f"Hello you too {consumer.user.username}!"
        msg = HelloResponse(greeting=greeting)
        await msg.async_send(consumer.channel_name, message_id=message_id)


@websocket_outgoing_messages("testing.hello")
class HelloResponse(AbstractOutgoingMessage):
    greeting: str


def greet_user(user, consumer_name, message_id=None):
    greeting = f"Welcome {user.username}!"
    msg = HelloResponse(greeting=greeting)
    msg.send(consumer_name, message_id=message_id)


@receiver(client_connect)
def say_hello_at_connect(user, consumer_name, **kw):
    print("Saying hello")
    greet_user(user, consumer_name)
