from __future__ import annotations

from abc import ABC, abstractmethod

from asgiref.sync import async_to_sync
from channels import DEFAULT_CHANNEL_LAYER
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db.models import Model
from django.utils.functional import cached_property
from pydantic import validator
from pydantic.main import BaseModel
from typing import Optional, Type, Dict, Union, TYPE_CHECKING, Any

from voteit.core.queues import DEFAULT_QUEUE
from voteit.messaging import (
    MESSAGE_WAITING,
    MESSAGE_RUNNING,
    MESSAGE_SUCCESS,
    MESSAGE_FAILED,
    INTERNAL_MESSAGE,
)
from voteit.messaging.envelopes import (
    IncomingEnvelope,
    InternalEnvelope,
    OutgoingEnvelope,
)

from voteit.messaging.utils import get_incoming_registry, get_outgoing_registry

if TYPE_CHECKING:
    from voteit.core.component import Registry

User = get_user_model()


class MessageMeta(BaseModel):
    message_id: Optional[str]
    type: str
    user_pk: Optional[int]
    consumer_name: Optional[str]


class IncomingMeta(MessageMeta):
    internal: bool = False

    @validator("type")
    def validate_type(cls, v):
        registry = get_incoming_registry()
        if v not in registry:
            raise ValueError("No such message type")
        return v


class OutgoingMeta(MessageMeta):
    @validator("type")
    def validate_type(cls, v):
        registry = get_outgoing_registry()
        if v not in registry:
            raise ValueError("No such message type")
        return v


class NoPayload(BaseModel):
    pass


class MessageABC(ABC):
    mm: Union[IncomingMeta, OutgoingMeta]
    data: BaseModel
    registry: Registry
    channel_layer_name: str = DEFAULT_CHANNEL_LAYER
    schema: Type[BaseModel] = NoPayload
    # State constants
    WAITING = MESSAGE_WAITING
    RUNNING = MESSAGE_RUNNING
    SUCCESS = MESSAGE_SUCCESS
    FAILED = MESSAGE_FAILED

    @property
    @abstractmethod
    def name(self) -> str:
        """ The ID/name of the command or query. This corresponds to 't' on incoming messages.
        """

    @staticmethod
    @abstractmethod
    def get_registry() -> Registry:
        """ The used registry for this type.
        """

    @cached_property
    def user(self) -> Optional[AbstractUser]:
        """ Retrieve user from MessageMeta.user_pk, if it exists"""
        if self.mm.user_pk:
            return User.objects.filter(pk=self.mm.user_pk).first()
        return None

    @cached_property
    def channel_layer(self):
        return get_channel_layer(self.channel_layer_name)

    def send_internal(self, channel_name: str, group: bool = False):
        return async_to_sync(self.async_send_internal)(channel_name, group=group)

    async def async_send_internal(self, channel_name: str, group: bool = False):
        envelope = InternalEnvelope(p=self.data, i=self.mm.message_id, t=self.mm.type)
        if group:
            await self.channel_layer.group_send(channel_name, envelope.dict())
        else:
            await self.channel_layer.send(channel_name, envelope.dict())

    def send_outgoing(
        self,
        channel_name: str,
        state: Optional[str] = None,
        success: Optional[bool] = None,
        group: bool = False,
    ):
        return async_to_sync(self.async_send_outgoing)(
            channel_name, state=state, success=success, group=group
        )

    async def async_send_outgoing(
        self,
        channel_name: str,
        state: Optional[str] = None,
        success: Optional[bool] = None,
        group: bool = False,
    ):
        if success is not None:
            if state is not None:
                raise ValueError("Can't specify both state and success")
            if success:
                state = self.SUCCESS
            else:
                state = self.FAILED
        print(f" mm.type is: {self.mm.type} of class {self}")
        envelope = OutgoingEnvelope(
            p=self.data, i=self.mm.message_id, t=self.mm.type, s=state
        )
        if group:
            await self.channel_layer.group_send(channel_name, envelope.dict())
        else:
            await self.channel_layer.send(channel_name, envelope.dict())


class BaseIncomingMessage(MessageABC):
    def __init__(self, mm: Union[Dict, IncomingMeta], data: Dict):
        self.mm = isinstance(mm, IncomingMeta) and mm or IncomingMeta(**mm)
        self.data = self.schema(**data)

    @classmethod
    def from_consumer(
        cls, consumer, envelope: Union[IncomingEnvelope, InternalEnvelope]
    ):
        mm = IncomingMeta(
            consumer_name=consumer.channel_name,
            user_pk=consumer.user.pk,
            message_id=envelope.i,
            type=envelope.t,
            internal=getattr(envelope, "type", None) == INTERNAL_MESSAGE,
        )
        msg_cls = cls.get_registry()[mm.type]  # Already validated
        inst = msg_cls(mm, envelope.p)
        inst.user = consumer.user  # This will be the same anyway
        return inst

    @staticmethod
    def get_registry() -> Registry:
        return get_incoming_registry()


class BaseOutgoingMessage(MessageABC):
    def __init__(self, mm: Union[Dict, OutgoingMeta], data: Dict):
        self.mm = isinstance(mm, OutgoingMeta) and mm or OutgoingMeta(**mm)
        self.data = self.schema(**data)

    @staticmethod
    def get_registry() -> Registry:
        return get_outgoing_registry()

    @classmethod
    def from_incoming(
        cls, message: BaseIncomingMessage, type_name=None, **kwargs
    ) -> BaseOutgoingMessage:
        if type_name is None:
            assert (
                cls.name is not None
            ), "You need to specify type name, this is an abstract class"
            type_name = cls.name
        mm = OutgoingMeta(type=type_name, **message.mm.dict(exclude={"type"}))
        return cls.get_registry()[type_name](mm, kwargs)

    @classmethod
    def create(
        cls, type_name=None, message_id=None, consumer_name=None, user_pk=None, **kwargs
    ):
        if type_name is None:
            assert (
                cls.name is not None
            ), "You need to specify type name, this is an abstract class"
            type_name = cls.name
        mm = OutgoingMeta(
            type=type_name,
            message_id=message_id,
            consumer_name=consumer_name,
            user_pk=user_pk,
        )
        return cls.get_registry()[type_name](mm, kwargs)


class ContextSchema(BaseModel):
    """ Use this as a mixin for your schema if it's for a specific model. """

    pk: int


class ContextMessageABC(MessageABC):
    """ This is used on a specific database instance and may have a permission. """

    schema: Type[ContextSchema]

    def __new__(cls, *args, **kwargs):
        assert issubclass(cls.schema, ContextSchema)
        return cls.__new__(*args, **kwargs)

    @property
    @abstractmethod
    def permission(self) -> Optional[str]:
        pass

    @property
    @abstractmethod
    def Model(self) -> Type[Model]:
        pass

    def allowed(self) -> bool:
        if self.user is None:
            return False
        if self.context is None:
            return False
        if self.permission is None:
            return True
        return self.user.has_perm(self.permission, self.context)

    @cached_property
    def context(self) -> Model:
        return self.Model.objects.get(pk=self.data.pk)


class AsyncRunnable(BaseIncomingMessage, ABC):
    """ This message is ment to be processed within the consumer.
        It mustn't be blocking or run database queries.
        Anything locking up the consumer will cause it to stop processing messages for that user.
    """

    @abstractmethod
    async def run(self):
        pass


class DeferredJob(BaseIncomingMessage, ABC):
    """ Command/query can be deferred to a job queue."""

    queue = DEFAULT_QUEUE
    job_timeout = 7
    autocommit = True
    is_async = True
    job_func = "voteit.messaging.jobs.handle_job_message"
    job_atomic = True
    on_worker = False
    # Markers for type checking
    mm: IncomingMeta
    data: Any  # But really the schema

    async def pre_queue(self, consumer):
        """ Do something before entering the queue. Only applies to when the consumer receives the message.
            It's a good idea to avoid using this if it's not needed.
        """

    def enqueue(self):
        # FIXME: Queues and django_rq are kind of a mess right now
        from voteit.messaging.jobs import run_job

        run_job.delay(msg_data=self.data.dict(), mm_data=self.mm.dict(), atomic=True)

        # kwargs = dict(
        #     atomic=self.job_atomic,
        #      msg_data=self.data.dict(),
        #      mm_data=self.mm.dict(),
        # )
        # queue = get_queue(name=self.queue, is_async=self.is_async, serializer=JSONSerializer)
        # job = Job.create("voteit.messaging.jobs.run_job", timeout=self.job_timeout, kwargs=kwargs)
        # queue.enqueue("voteit.messaging.jobs.run_job", timeout=self.job_timeout, kwargs=kwargs)

        # queue.enqueue(job)

        # queue = get_queue(
        #     self.queue,
        #     autocommit=self.autocommit,
        #     #default_timeout=self.job_timeout,
        #     is_async=self.is_async,
        #     serializer=JSONSerializer,
        # )
        # queue.enqueue(
        #     "voteit.messaging.jobs.run_job",
        #     job_timeout=self.job_timeout,
        #
        #     atomic=self.job_atomic,
        #     msg_data=self.data.dict(),
        #     mm_data=self.mm.dict(),
        # )

    @classmethod
    def from_job(cls, msg_data, mm_data):
        mm = IncomingMeta(**mm_data)
        msg_cls = cls.get_registry()[mm.type]
        instance = msg_cls(mm, msg_data)
        instance.on_worker = True
        return instance

    @abstractmethod
    def run_job(self):
        """ Run this within the worker to do the actual job"""
        pass
