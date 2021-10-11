from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from logging import getLogger
from typing import Dict, Generic, TypeVar
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type
from typing import Union

from asgiref.sync import async_to_sync
from channels import DEFAULT_CHANNEL_LAYER
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db import transaction
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from pydantic.main import BaseModel
from voteit.core.queues import DEFAULT_QUEUE
from voteit.messaging import INTERNAL_MESSAGE
from voteit.messaging import MESSAGE_FAILED
from voteit.messaging import MESSAGE_RUNNING
from voteit.messaging import MESSAGE_SUCCESS
from voteit.messaging import MESSAGE_WAITING
from voteit.messaging.envelopes import IncomingEnvelope
from voteit.messaging.envelopes import InternalEnvelope
from voteit.messaging.envelopes import OutgoingEnvelope
from voteit.messaging.utils import get_incoming_registry
from voteit.messaging.utils import get_outgoing_registry

if TYPE_CHECKING:
    from voteit.core.component import Registry
    from channels_redis.core import RedisChannelLayer
    from voteit.messaging.consumers import WebsocketDemuxConsumer


logger = getLogger(__name__)


class MessageMeta(BaseModel):
    message_id: Optional[str]
    type: str  # Validation is handled by the envelope instead
    user_pk: Optional[int]
    consumer_name: Optional[str]
    internal: bool = False
    language: Optional[str] = None


class NoPayload(BaseModel):
    pass


class MessageABC(ABC):
    mm: MessageMeta
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
        """The ID/name of the command or query. This corresponds to 't' on incoming messages."""

    @staticmethod
    @abstractmethod
    def get_registry() -> Registry:
        """The used registry for this type."""

    @classmethod
    @abstractmethod
    def from_message(cls, message: MessageABC, type_name=None, **kwargs) -> MessageABC:
        pass

    @property
    def is_on_commit_disabled(self):
        return getattr(settings, "DISABLE_MESSAGE_ON_COMMIT", False)

    def __init__(
        self,
        mm: Union[Dict, MessageMeta] = None,
        data: Optional[Dict] = None,
        **kwargs,
    ):
        if mm is None:
            mm = {}
        if isinstance(mm, MessageMeta):
            self.mm = mm
        else:
            assert isinstance(self.name, str), "Name attribute is not set as a string"
            mm["type"] = self.name
            self.mm = MessageMeta(**mm)
        if data is None:
            data = {}
        data.update(kwargs)
        self.data = self.schema(**data)

    @cached_property
    def user(self) -> Optional[AbstractUser]:
        """Retrieve user from MessageMeta.user_pk, if it exists"""
        if self.mm.user_pk:
            User: AbstractUser = get_user_model()
            return User.objects.filter(pk=self.mm.user_pk).first()
        return None

    @cached_property
    def channel_layer(self):
        return get_channel_layer(self.channel_layer_name)

    def send_internal(self, channel_name: str, group: bool = False, on_commit=True):
        """Queue an internal message, meant for the consumer and not to be transmitted over websocket.
        These are usually actions that need to be taken by the consumers, like healthchecks.
        """

        def _hook():
            async_to_sync(self.async_send_internal)(channel_name, group=group)

        if on_commit and not self.is_on_commit_disabled:
            transaction.on_commit(_hook)
        else:
            _hook()

    async def async_send_internal(
        self, channel_name: str, group: bool = False, on_commit=None
    ):
        assert on_commit is None, "This argument doesn't work on async calls!"
        envelope = InternalEnvelope(
            p=self.data.json(),
            i=self.mm.message_id,
            t=self.mm.type,
            l=self.mm.language,
            incoming=isinstance(self, BaseIncomingMessage),
        )
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
        on_commit: bool = True,
    ):
        """Queue a message that the consumer is meant to deliver over websocket to the client.
        The message may also contain actions that'll be taken before the message is transmitted.
        """

        def _hook():
            async_to_sync(self.async_send_outgoing)(
                channel_name, state=state, success=success, group=group
            )

        if on_commit and not self.is_on_commit_disabled:
            transaction.on_commit(_hook)
        else:
            _hook()

    async def async_send_outgoing(
        self,
        channel_name: str,
        state: Optional[str] = None,
        success: Optional[bool] = None,
        group: bool = False,
        on_commit=None,
    ):
        """Async call to queue an outgoing message. Use this directly when possible.
        Note that it doesn't support transactions so it will be queued directly.
        """
        assert on_commit is None, "This argument doesn't work on async calls!"
        if success is not None:
            if state is not None:
                raise ValueError("Can't specify both state and success")
            if success:
                state = self.SUCCESS
            else:
                state = self.FAILED
        envelope = OutgoingEnvelope(
            p=self.data.json(),
            i=self.mm.message_id,
            t=self.mm.type,
            s=state,
            l=self.mm.language,
        )
        if group:
            await self.channel_layer.group_send(channel_name, envelope.dict())
        else:
            await self.channel_layer.send(channel_name, envelope.dict())

    @classmethod
    def from_consumer(
        cls,
        consumer,
        envelope: Union[IncomingEnvelope, InternalEnvelope, OutgoingEnvelope],
    ):
        """Instantiate a message with details from the consumer and an envelope."""
        mm = MessageMeta(
            consumer_name=consumer.channel_name,
            user_pk=consumer.user.pk,
            message_id=envelope.i,
            type=envelope.t,
            internal=getattr(envelope, "type", None) == INTERNAL_MESSAGE,
            language=envelope.l,
        )
        msg_cls = cls.get_registry()[mm.type]  # Already validated
        inst = msg_cls(mm, envelope.p)
        inst.user = consumer.user  # This will be the same anyway
        return inst

    @classmethod
    def create(
        cls,
        type_name=None,
        message_id=None,
        consumer_name=None,
        user_pk=None,
        language=None,
        **kwargs,
    ):
        if type_name is None:
            assert (
                cls.name is not None
            ), "You need to specify type name, this is an abstract class"
            type_name = cls.name
        mm = MessageMeta(
            type=type_name,
            message_id=message_id,
            consumer_name=consumer_name,
            user_pk=user_pk,
            language=language,
        )
        return cls.get_registry()[type_name](mm, kwargs)


class BaseIncomingMessage(MessageABC, ABC):
    """A message that might be received from websocket or picked up internally.

    Only these kinds of messages can be received through sockets.

    It's registered in the incoming registry and works as an API.
    """

    @staticmethod
    def get_registry() -> Registry:
        return get_incoming_registry()

    @classmethod
    def from_message(
        cls, message: MessageABC, type_name=None, **kwargs
    ) -> BaseIncomingMessage:
        if type_name is None:
            assert (
                cls.name is not None
            ), "You need to specify type name, this is an abstract class"
            type_name = cls.name
        mm = MessageMeta(type=type_name, **message.mm.dict(exclude={"type"}))
        return cls.get_registry()[type_name](mm, kwargs)


class BaseOutgoingMessage(MessageABC, ABC):
    """A message that may be transmitted and processed within the consumer or delegated and sent to the websocket.
    These kind of messages are registered as outgoing and should be treated as expected responses.
    """

    @staticmethod
    def get_registry() -> Registry:
        return get_outgoing_registry()

    @classmethod
    def from_message(
        cls, message: MessageABC, type_name=None, **kwargs
    ) -> BaseOutgoingMessage:
        if type_name is None:
            assert (
                cls.name is not None
            ), "You need to specify type name, this is an abstract class"
            type_name = cls.name
        mm = MessageMeta(type=type_name, **message.mm.dict(exclude={"type"}))
        return cls.get_registry()[type_name](mm, kwargs)


class AsyncRunnable(ABC):
    """
    This message is meant to be processed within the consumer.
    It mustn't be blocking or run database queries.
    Anything locking up the consumer will cause it to stop processing messages for that user.
    """

    @abstractmethod
    async def run(self, consumer: WebsocketDemuxConsumer):
        pass


class DeferredJob(ABC):
    """Command/query can be deferred to a job queue.
    Must be used together with BaseIncomingMessage or BaseOutgoingMessage"""

    queue = DEFAULT_QUEUE
    # job_timeout = 7
    # autocommit = True
    # is_async = True
    job_func = "voteit.messaging.jobs.handle_job_message"
    # job_atomic = True
    on_worker = False
    # Markers for type checking
    mm: MessageMeta
    data: BaseModel  # But really the schema
    should_run: bool = True  # Mark as false to abort run

    async def pre_queue(self, consumer: WebsocketDemuxConsumer):
        """Do something before entering the queue. Only applies to when the consumer receives the message.
        It's a good idea to avoid using this if it's not needed.
        """

    def enqueue(self, queue=None):
        # FIXME: Queues and django_rq are kind of a mess right now
        from voteit.messaging.jobs import run_job

        if not self.should_run:
            return
        kwargs = dict(
            msg_data=self.data.dict(),  # FIXME: Json encode instead?
            mm_data=self.mm.dict(),
            incoming=isinstance(self, BaseIncomingMessage),
            atomic=True,
        )
        if queue:
            return queue.enqueue(run_job, **kwargs)
        # Job-decorated queue
        return run_job.delay(**kwargs)

        # kwargs = dict(
        #     atomic=self.job_atomic,
        #      msg_data=self.data.dict(),
        #      mm_data=self.mm.dict(),
        # )
        # queue = get_queue(name=self.queue, is_async=self.is_async, serializer=JSONSerializer)
        # queue.enqueue("voteit.messaging.jobs.run_job", timeout=self.job_timeout, kwargs=kwargs)

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
    def from_job(
        cls, msg_data, mm_data, incoming=True
    ) -> Union[DeferredJob, MessageABC]:
        if incoming:
            registry = get_incoming_registry()
        else:
            registry = get_outgoing_registry()
        mm = MessageMeta(**mm_data)
        # Key error here would be a programming error, not a validation error
        msg_cls = registry[mm.type]
        instance = msg_cls(mm, msg_data)
        instance.on_worker = True
        return instance

    @abstractmethod
    def run_job(self):
        """Run this within the worker to do the actual job"""
        pass


M = TypeVar(
    "M"
)  # Inherit ContextAction using ContextAction[Model] for correct type annotation of context.


class ContextAction(MessageABC, ABC, Generic[M]):
    """An action performed on a specific context.
    It has a permission and a model. The schema itself must contain an attribute that will be
    used for lookup of the context to perform the action on. (context_pk_attr)

    Note that it only works as a placeholder for an action, the code itself should be constructed by
    combining it with DeferredJob and must also inherit BaseIncomingMessage or BaseOutgoingMessage
    """

    @property
    @abstractmethod
    def context_pk_attr(self) -> str:
        """Fetch context from this attribute in the schema"""

    @property
    @abstractmethod
    def schema(self) -> Type[BaseModel]:
        """This really must have a valid schema"""

    @property
    @abstractmethod
    def permission(self) -> Optional[str]:
        """Text permission, None means allow any."""

    @property
    @abstractmethod
    def model(self) -> Type[models.Model]:
        """Model class this operates on."""

    def allowed(self) -> bool:
        if self.user is None:
            return False
        if self.context is None:
            return False
        if self.permission is None:
            return True
        return self.user.has_perm(self.permission, self.context)

    @cached_property
    def context(self) -> M:
        try:
            pk = getattr(self.data, self.context_pk_attr)
        except AttributeError:
            raise AttributeError(
                f"{self.context_pk_attr} is not a valid schema attribute for pk lookup. Message: {self}"
            )
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            raise BaseError.create(
                type_name="error.not_found",
                consumer_name=self.mm.consumer_name,
                permission=self.permission,
                msg=_(
                    "No %(context)s with pk %(pk)s"
                    % {"context": self.model, "pk": self.data.pk}
                ),
            )

    def assert_perm(self, msg=None):
        if not self.allowed():
            raise BaseError.from_message(
                self,
                type_name="error.unauthorized",  # Constant?
                permission=self.permission,
                msg=msg,  # None is default
            )


class ErrorSchema(BaseModel):
    msg: Optional[str]


class BaseError(BaseOutgoingMessage, Exception, ABC):
    schema = ErrorSchema
    data: ErrorSchema
    default_msg = _("An unknown error occurred")

    @classmethod
    def create(
        cls,
        type_name=None,
        message_id=None,
        consumer_name=None,
        language=None,
        user_pk=None,
        msg=None,
        **kwargs,
    ):
        inst = super().create(
            type_name=type_name,
            message_id=message_id,
            consumer_name=consumer_name,
            user_pk=user_pk,
            language=None,
            **kwargs,
        )
        assert isinstance(inst, BaseError), f"Error is not inherited from {BaseError}"
        assert inst.name.startswith("error."), "Error names must start with 'error.'"
        if msg is None and inst.default_msg is not None:
            msg = inst.default_msg
        inst.data.msg = msg
        return inst

    def send_outgoing(
        self,
        channel_name: str,
        state: Optional[str] = None,
        success: Optional[bool] = None,
        group: bool = False,
        on_commit: bool = False,
    ):
        """Error messages should normally be sent directly, so default on_commit to false"""
        super(BaseError, self).send_outgoing(
            channel_name, state=state, success=success, group=group, on_commit=on_commit
        )

    async def async_send_outgoing(
        self,
        channel_name: str,
        state: Optional[str] = None,
        success: Optional[bool] = False,
        group: bool = False,
        on_commit=None,
    ):
        """Override and default to error."""
        assert on_commit is None, "This argument doesn't work on async calls!"
        if state is not None:
            assert state == self.FAILED, "Error messages must be sent as failed state"
        assert not success, "Error messages must be sent as failed state"
        await super().async_send_outgoing(channel_name, success=False, group=group)


class AbstractChannel(ABC):
    """Classic publish/subscribe pattern. This represents a channel that a consumer (websocket connection)
    can subscribe to.
    """

    logger = logger
    channel_layer: RedisChannelLayer  # FIXME?
    consumer_channel: Optional[str]

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the channel factory, not the specific channel name."""
        pass

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Return name of this channel, probably based on the primary key of an object"""
        pass

    def __init__(
        self,
        consumer_channel: Optional[str] = None,
        channel_layer: Optional[RedisChannelLayer] = None,
    ):
        self.channel_layer = channel_layer and channel_layer or get_channel_layer()
        self.consumer_channel = consumer_channel

    @property
    def is_on_commit_disabled(self):
        return getattr(settings, "DISABLE_MESSAGE_ON_COMMIT", False)

    @classmethod
    def from_consumer(cls, consumer: WebsocketDemuxConsumer, channel_name=None):
        return cls(
            consumer_channel=consumer.channel_name, channel_layer=consumer.channel_layer
        )

    async def async_subscribe(self, consumer_channel=None):
        if consumer_channel is None:
            consumer_channel = self.consumer_channel
        assert consumer_channel
        # self.logger.debug("Subscribed to %s", self.channel_name)
        await self.channel_layer.group_add(self.channel_name, consumer_channel)

    def subscribe(self, consumer_channel=None):
        async_to_sync(self.async_subscribe)(consumer_channel=consumer_channel)

    async def async_publish(
        self, message: MessageABC, internal=False, on_commit=None, **kwargs
    ):
        # self.logger.debug("Publish to %s", self.channel_name)
        assert on_commit is None, "This argument doesn't work on async calls!"
        assert isinstance(message, MessageABC)
        if internal:
            await message.async_send_internal(self.channel_name, group=True)
        else:
            await message.async_send_outgoing(self.channel_name, group=True, **kwargs)

    def publish(self, message: MessageABC, internal=False, on_commit=True, **kwargs):
        def _hook():
            async_to_sync(self.async_publish)(message, internal=internal, **kwargs)

        if on_commit and not self.is_on_commit_disabled:
            transaction.on_commit(_hook)
        else:
            _hook()

    async def async_leave(self, consumer_channel=None):
        if consumer_channel is None:
            consumer_channel = self.consumer_channel
        assert consumer_channel
        # self.logger.debug("Left %s", self.channel_name)
        await self.channel_layer.group_discard(self.channel_name, consumer_channel)

    def leave(self, consumer_channel=None):
        async_to_sync(self.async_leave)(consumer_channel=consumer_channel)


class AbstractObjectChannel(AbstractChannel):
    """A channel that has to do with a specific object. For instance, the agenda channel is related to a meeting."""

    logger = logger
    pk: int  # Primary key of the object that this channel is about

    def __init__(
        self,
        pk: int,
        consumer_channel: Optional[str] = None,
        channel_layer: Optional[RedisChannelLayer] = None,
    ):
        self.pk = pk
        super(AbstractObjectChannel, self).__init__(consumer_channel, channel_layer)

    @property
    def channel_name(self) -> str:
        return f"{self.name}_{self.pk}"

    @property
    @abstractmethod
    def model(self) -> models.Model:
        """Set as property on subclass. Model should be the type of model this object channel is for."""
        pass

    @property
    @abstractmethod
    def permission(self) -> str:
        """Set as property on subclass. The permission to evaluate subscribe commands against."""
        pass

    @classmethod
    def from_pk(
        cls, pk: int, consumer_channel: Optional[str] = None
    ) -> AbstractObjectChannel:
        return cls(pk, consumer_channel)

    @classmethod
    def from_instance(
        cls, instance: models.Model, consumer_channel: Optional[str] = None
    ) -> AbstractObjectChannel:
        assert isinstance(instance, cls.model), f"Instance must be a {cls.model}"
        inst = cls.from_pk(instance.pk, consumer_channel)
        inst.context = instance
        return inst

    @cached_property
    def context(self) -> models.Model:
        try:
            return self.model.objects.get(pk=self.pk)
        except self.model.DoesNotExist:
            raise BaseError.create(
                type_name="error.not_found",
                consumer_name=self.consumer_channel,
                msg=_("Context for this channel doesn't exist"),
            )

    def allow_subscribe(self, user):
        """Call this before subscribing. Due to sync/async and the complexity of
        permissions this won't be enforced before calling subscribe.
        """
        if user is None:
            return False
        if self.context is None:
            return False
        if self.permission is None:
            return True
        return user.has_perm(self.permission, self.context)

    def allow_publish(self, user):
        """Override and call this before publishing. Due to sync/async and the complexity of
        permissions this won't be enforced before calling publish.

        Defaulting to false is ok here
        """
        return False

    def allow_leave(self, user):
        """Override and call this before leaving. Due to sync/async and the complexity of
        permissions this won't be enforced before calling leave.

        Leave shouldn't require the same permission checks so we'll settle on allowing this as default.
        """
        return True
