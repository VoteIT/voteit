from __future__ import annotations

from time import sleep
from typing import TYPE_CHECKING, Optional

from django.dispatch import receiver
from django_rq import job
from pydantic import validator
from voteit.messaging.messages import MsgState
from voteit.messaging.messages.abcs import AbstractIncomingMessage, AbstractOutgoingMessage
from voteit.messaging.messages.progress import ProgressNum
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
        await msg.async_send(consumer.channel_name, message_id=message_id, state=MsgState.SUCCESS)


@websocket_outgoing_messages("testing.hello")
class HelloResponse(AbstractOutgoingMessage):
    greeting: str


def greet_user(user, consumer_name, message_id=None):
    greeting = f"Welcome {user.username}!"
    msg = HelloResponse(greeting=greeting)
    msg.send(consumer_name, message_id=message_id, state=MsgState.SUCCESS)


@receiver(client_connect)
def say_hello_at_connect(user, consumer_name, **kw):
    print("Saying hello")
    greet_user(user, consumer_name)


@websocket_incoming_messages("testing.count")
class Count(AbstractIncomingMessage):
    num: int = 10
    fail: Optional[int]

    @validator("num")
    def check_num(cls, v):
        if v > 10:
            raise ValueError(f"{v} is higher than 10")
        if v < 1:
            raise ValueError(f"{v} must be at least 1")
        return v

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        msg = ProgressNum(curr=0, total=self.num, msg=f"We're about to count to {self.num}.")
        await msg.async_send(consumer.channel_name, message_id=message_id, state=MsgState.WAITING)
        count_to_num.delay(consumer_name=consumer.channel_name, num=self.num, message_id=message_id, fail=self.fail)


@job("default", timeout=20)
def count_to_num(consumer_name:str, num:int, message_id: str, fail:Optional[int] = None):
    # Start at 0, before we waited!
    text = f"Let's count to {num}!"
    if fail:
        text += f" ...But fail at {fail}"
    msg = ProgressNum(curr=0, total=num, msg=text)
    msg.send(consumer_name, message_id, state=MsgState.RUNNING)
    sleep(1)
    for i in range(1, num):
        if fail and fail == i:
            msg = ProgressNum(curr=i, total=num, msg=f"Deliberate fail at {fail}")
            msg.send(consumer_name, message_id, state=MsgState.FAILED)
            return
        else:
            msg = ProgressNum(curr=i, total=num)
            msg.send(consumer_name, message_id, state=MsgState.RUNNING)
        sleep(1)
    msg = ProgressNum(curr=num, total=num, msg="All done!")
    msg.send(consumer_name, message_id, state=MsgState.SUCCESS)
