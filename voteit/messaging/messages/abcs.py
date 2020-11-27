from __future__ import annotations

from abc import ABC, abstractmethod
from logging import getLogger
from typing import TYPE_CHECKING, Optional, Dict

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db.models import Model
from django_rq import get_queue
from pydantic import BaseModel
from voteit.core.queues import DEFAULT_QUEUE

from voteit.messaging.messages import OutgoingPayload, MsgState
from voteit.messaging.messages import WEBSOCKET_OUTGOING_NAME
from voteit.messaging.messages import INTERNAL_MESSAGE
from voteit.messaging.messages import MessageContext

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


User = get_user_model()
logger = getLogger(__name__)


class AbstractMessage(BaseModel, ABC):
    """ Any kind of message being passed through channels/websockets
    """

    pass


class AbstractIncomingMessage(AbstractMessage):
    """ A message received from websocket. It's then consumed within the consumer context.
    """
    mc: MessageContext


class AbstractConsumerMessage(AbstractIncomingMessage):
    """ A message that's meant to be consumed right away within the consumer
    """

    @abstractmethod
    async def consume(self, consumer: WebsocketDemuxConsumer):
        pass


class JobDefault:
    """ Defaults """
    queue = DEFAULT_QUEUE
    timeout = 20
    autocommit = True
    is_async = True


class AbstractJobMessage(AbstractIncomingMessage):

    async def consume(self, consumer: WebsocketDemuxConsumer):
        await self.pre_queue(consumer=consumer)
        queue = get_queue(
            getattr(self.Job, "queue", "default"),
            autocommit=getattr(self.Job, "autocommit", True),
            is_async=getattr(self.Job, "is_async", True),
            default_timeout=getattr(self.Job, "timeout", 20),
            # serializer=json,  # FIXME doesn't work
        )
        queue.enqueue(
            "voteit.messaging.jobs.handle_job_message", msg_type=self.mc.type, msg_data=self.dict()
        )

    async def pre_queue(self, consumer: WebsocketDemuxConsumer):
        """ Called when message is finished and about to be queued.
            Only use non-blocking async code here - no db lookups!
        """

    @abstractmethod
    def job(self):
        pass

    class Job(JobDefault):
        pass

    def get_user(self) -> Optional[AbstractUser]:
        if self.mc.user_pk:
            return User.objects.get(pk=self.mc.user_pk)


DEFAULT_NEVER = "__never"

class ContextJobDefault(JobDefault):
    """ Defaults """
    permission = DEFAULT_NEVER
    model = None


class AbstractContextJobMessage(AbstractJobMessage):
    """ Assumes an action that will be perormed in a worker. The action is on a specific context,
        so it will need A pk, a permission and a model.
    """
    pk: int

    class Job(ContextJobDefault):
        pass

    def get_context(self):
        assert issubclass(self.Job.model, Model)
        return self.Job.model.objects.get(pk=self.pk)

    def allowed(self, user, context):
        if user is None:
            return False
        if context is None:
            return False
        perm = self.Job.permission
        if perm == DEFAULT_NEVER:
            return False
        if perm is None:
            return True
        return user.has_perm(perm, context)


class AbstractTransmittableMessage(AbstractMessage):
    """ A message that's meant to be serialized and transmitted somewhere.
        Note the difference in sync and async methods.
    """

    @abstractmethod
    def format_payload(
        self, message_id: Optional[str], state: str = "", success: Optional[bool] = None
    ):
        pass

    async def async_send(
        self,
        channel: str,
        message_id: Optional[str] = None,
        state="",
        success: Optional[bool] = None,
    ):
        """
        :param channel: ID of the channel to send this to
        :param message_id:
        :param state: MsgState, one letter
        :param success:
        :return:
        """
        payload = self.format_payload(message_id, state=state, success=success)
        channel_layer = get_channel_layer()
        await channel_layer.send(channel, payload)

    async def async_group_send(
        self,
        channel: str,
        message_id: Optional[str] = None,
        state: str = "",
        success: Optional[bool] = None,
    ):
        payload = self.format_payload(message_id, state=state, success=success)
        channel_layer = get_channel_layer()
        print("Async sending to: ", channel)
        await channel_layer.group_send(channel, payload)

    def send(
        self,
        channel: str,
        message_id: Optional[str] = None,
        state: str = "",
        success: Optional[bool] = None,
    ):
        payload = self.format_payload(message_id, state=state, success=success)
        channel_layer = get_channel_layer()
        print("Sending to: ", channel)
        async_to_sync(channel_layer.send)(channel, payload)

    def group_send(
        self,
        channel: str,
        message_id: Optional[str] = None,
        state: str = "",
        success: Optional[bool] = None,
    ):
        payload = self.format_payload(message_id, state=state, success=success)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(channel, payload)


class AbstractInternalMessage(AbstractConsumerMessage, AbstractTransmittableMessage):
    """ A message received internally from channels. It can be both transmittable and consumable.
        If this type of message is received via websocket, it will cause an error.
    """

    def format_payload(
        self, message_id: Optional[str], state: str = "", success: Optional[bool] = None
    ):
        from voteit.messaging.registries import internal_messages

        if success is not None:
            if success:
                state = MsgState.SUCCESS
            else:
                state = MsgState.FAILED

        for (mtype, MessageType) in internal_messages.items():
            if self.__class__ == MessageType:
                return {
                    "type": INTERNAL_MESSAGE,
                    "p": self.json(),
                    "t": mtype,
                    "i": message_id,
                    "s": state,
                }
        raise KeyError(
            f"{self.__class__} not found in internal_messages registry, register the message type there first"
        )


class AbstractOutgoingMessage(AbstractTransmittableMessage):
    def format_payload(
        self, message_id: Optional[str], state: str = "", success: Optional[bool] = None
    ):
        from voteit.messaging.registries import websocket_outgoing_messages

        if success is not None:
            if success:
                state = MsgState.SUCCESS
            else:
                state = MsgState.FAILED

        for (mtype, MessageType) in websocket_outgoing_messages.items():
            if self.__class__ == MessageType:
                payload = OutgoingPayload(p=self, t=mtype, i=message_id, s=state)
                return {"type": WEBSOCKET_OUTGOING_NAME, "payload": payload.json()}

        raise KeyError(
            f"{self.__class__} not found in websocket_outgoing_messages registry, register the message type there first"
        )


class AddObject(AbstractIncomingMessage):
    data: Dict


class ChangeObject(AbstractIncomingMessage):
    pk: int
    data: Dict


class DeleteObject(AbstractIncomingMessage):
    pk: int


class ObjectAdded(AbstractOutgoingMessage):
    item: Dict


class ObjectChanged(AbstractOutgoingMessage):
    item: Dict


class ObjectDeleted(AbstractOutgoingMessage):
    pk: int
