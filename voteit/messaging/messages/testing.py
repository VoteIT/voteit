from __future__ import annotations

from time import sleep
from typing import TYPE_CHECKING, Optional, List

from django.dispatch import receiver
from django_rq import job
from pydantic import validator, BaseModel

#from voteit.messaging.messages import MsgState
#from voteit.messaging.messages.abcs import AbstractIncomingMessage, AbstractOutgoingMessage, AbstractJobMessage
from voteit.messaging.abcs import BaseIncomingMessage, BaseOutgoingMessage, DeferredJob, AsyncRunnable
from voteit.messaging.messages.progress import ProgressNum
from voteit.messaging.models import Connection
from voteit.messaging.registries import incoming_messages, outgoing_messages
from voteit.messaging.signals import client_connect

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


@incoming_messages
class Hello(AsyncRunnable):
    name = "testing.hello"

    async def run(self):
        greeting = f"Hello you too {self.user.username}!"
        msg = HelloResponse.from_incoming(self, greeting=greeting)
        await msg.async_send_outgoing(self.mm.consumer_name, success=True)


class Greeting(BaseModel):
    greeting: str


@outgoing_messages
class HelloResponse(BaseOutgoingMessage):
    name = "testing.hello"
    schema = Greeting


def greet_user(user, consumer_name, message_id=None):
    greeting = f"Welcome {user.username}!"
    msg = HelloResponse.create(message_id=message_id, greeting=greeting)
    msg.send_outgoing(consumer_name, success=True)


@receiver(client_connect)
def say_hello_at_connect(user, consumer_name, **kw):
    print("Saying hello")
    greet_user(user, consumer_name)


class CountSchema(BaseModel):
    num: int = 10
    fail: Optional[int]

    @validator("num")
    def check_num(cls, v):
        if v > 10:
            raise ValueError(f"{v} is higher than 10")
        if v < 1:
            raise ValueError(f"{v} must be at least 1")
        return v


@incoming_messages
class Count(DeferredJob):
    name="testing.count"
    schema = CountSchema
    data: CountSchema

    async def pre_queue(self, consumer: WebsocketDemuxConsumer):
        msg = ProgressNum.from_incoming(self, curr=0, total=self.data.num, msg=f"We're about to count to {self.data.num}.")
        await msg.async_send_outgoing(consumer.channel_name, state=self.WAITING)

    def run_job(self):
        print("Running!")
        num = self.data.num
        fail = self.data.fail
        text = f"Let's count to {num}!"
        if self.data.fail:
            text += f" ...But fail at {fail}"
        msg = ProgressNum.from_incoming(self, curr=0, total=num,
                                        msg=text)
        msg.send_outgoing(self.mm.consumer_name, state=self.RUNNING)
        sleep(1)
        for i in range(1, num):
            if fail and fail == i:
                msg = ProgressNum.from_incoming(self, curr=i, total=self.num, msg=f"Deliberate fail at {self.fail}")

                msg = ProgressNum.from_incoming(self, curr=i, total=num,
                                                msg=f"Deliberate fail at {fail}")

                msg.send_outgoing(self.mm.consumer_name, success=False)
                return
            else:
                msg = ProgressNum.from_incoming(self, curr=i, total=num)
                msg.send_outgoing(self.mm.consumer_name, state=self.RUNNING)
            sleep(1)
        msg = ProgressNum.from_incoming(self, curr=num, total=num, msg="All done!")
        msg.send_outgoing(self.mm.consumer_name, success=True)
#
#
# @incoming_messages("testing.count")
# class Count(AbstractJobMessage):
#     num: int = 10
#     fail: Optional[int]
#
#     @validator("num")
#     def check_num(cls, v):
#         if v > 10:
#             raise ValueError(f"{v} is higher than 10")
#         if v < 1:
#             raise ValueError(f"{v} must be at least 1")
#         return v
#
#     async def pre_queue(self, consumer: WebsocketDemuxConsumer):
#         msg = ProgressNum(curr=0, total=self.num, msg=f"We're about to count to {self.num}.")
#         await msg.async_send(consumer.channel_name, message_id=self.mc.message_id, state=MsgState.WAITING)
#
#     def job(self):
#         text = f"Let's count to {self.num}!"
#         if self.fail:
#             text += f" ...But fail at {self.fail}"
#         msg = ProgressNum(curr=0, total=self.num, msg=text)
#         msg.send(self.mc.consumer_name, self.mc.message_id, state=MsgState.RUNNING)
#         sleep(1)
#         for i in range(1, self.num):
#             if self.fail and self.fail == i:
#                 msg = ProgressNum(curr=i, total=self.num, msg=f"Deliberate fail at {self.fail}")
#                 msg.send(self.mc.consumer_name, self.mc.message_id, success=False)
#                 return
#             else:
#                 msg = ProgressNum(curr=i, total=self.num)
#                 msg.send(self.mc.consumer_name, self.mc.message_id, state=MsgState.RUNNING)
#             sleep(1)
#         msg = ProgressNum(curr=self.num, total=self.num, msg="All done!")
#         msg.send(self.mc.consumer_name, self.mc.message_id, success=True)
#
#
# @incoming_messages("testing.online_users")
# class OnlineUsers(AbstractIncomingMessage):
#
#     async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
#         get_online_users.delay(consumer_name=consumer.channel_name, message_id=message_id)
#
#
# @outgoing_messages("testing.online_users")
# class OnlineUsersResponse(AbstractOutgoingMessage):
#     users: List[int]
#
#
# @job("default", timeout=5)
# def get_online_users(consumer_name: str, message_id: str):
#     users = Connection.objects.filter(online=True).distinct("user").values_list("user", flat=True)
#     msg = OnlineUsersResponse(users=list(users))
#     msg.send(consumer_name, message_id, success=True)
