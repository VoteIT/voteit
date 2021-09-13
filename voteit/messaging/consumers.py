import json
from contextlib import suppress
from datetime import datetime
from logging import getLogger
from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING
from typing import Union

from channels.auth import get_user
from channels.db import database_sync_to_async
from channels.exceptions import DenyConnection
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.utils import translation
from django.utils.timezone import now
from django.utils.translation import activate
from django.utils.translation import check_for_language
from django.utils.translation import get_supported_language_variant
from django.utils.translation.trans_real import get_languages
from django.utils.translation.trans_real import language_code_re
from django.utils.translation.trans_real import parse_accept_lang_header
from django_rq import get_queue
from pydantic import ValidationError
from rest_framework.authtoken.models import Token
from voteit.core.queues import DEFAULT_QUEUE
from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.envelopes import IncomingEnvelope
from voteit.messaging.envelopes import InternalEnvelope
from voteit.messaging.envelopes import OutgoingEnvelope
from voteit.messaging.errors import BaseError
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.jobs import signal_websocket_close
from voteit.messaging.jobs import signal_websocket_connect
from voteit.messaging.messages.channels import ChannelSubscription

logger = getLogger(__name__)

if TYPE_CHECKING:
    pass


# FIXME: We might need to check if channels properly cleans up groups
# They could fill up with messages fast in case no one is there to receive them.
# All clients won't send close signal, since they might just loose connection or go away for another reason.
# FIXME: Test full channels

# FIXME: Query consumer for last action


class WebsocketDemuxConsumer(AsyncWebsocketConsumer):
    """Demultiplexing consumer."""

    # User model, don't trust this since it will be wiped during logout procedure.
    user: Optional[AbstractUser] = None
    # The users pk associated with the connection. No anon connections are allowed at this time.
    # This will remain even if the user logs out. (The consumer will die shortly after logout)
    user_pk: Optional[int] = None
    # The specific connections own channel. Use this to send messages to one
    # specific connection or as id when subscribing to other channels.
    channel_name: str
    # Errors count, when these stack the sane response would be to simply disconnect
    message_errors: int = 0
    # Last sent, received
    last_sent: datetime = None
    last_recv: datetime = None
    last_error: Optional[datetime] = None
    protected_subscriptions: Dict[str, ChannelSubscription]
    # Send and queue connection signals?
    # They're a bad idea in most unit tests since they muck about with threading and db-access,
    # which causes the async tests to fail or start in another threads async event loop.
    enable_connection_signals: bool = True
    user_lang: Optional[str] = None

    def __init__(self, *args, enable_connection_signals=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.protected_subscriptions = {}
        self.enable_connection_signals = enable_connection_signals

    async def connect(self):
        self.user_lang = self.get_language()
        activate(self.user_lang)  # FIXME: Safe here?
        # try:
        #     connection_token = self.scope["url_route"]["kwargs"]["connection_token"]
        # except KeyError:
        #     connection_token = None
        # self.user = await self.get_token_user(key=connection_token)
        # if self.user is None:
        # FIXME: get_user ie refresh_user is the correct way to go
        # When using session auth instead of token:
        self.user = await self.refresh_user()
        if self.user is None:
            logger.debug("Invalid token, closing connection")
            raise DenyConnection()
        # Save for later use in case of invalidation of the user object
        self.user_pk = self.user.pk
        # And mark action
        self.last_sent = self.last_recv = now()
        logger.debug("Connection for user: %s", self.user)
        await self.accept()
        logger.debug(
            "Connection accepted for user %s (%s) with lang %s",
            self.user,
            self.user.pk,
            self.user_lang,
        )
        if self.enable_connection_signals:
            self.dispatch_connect()

    async def disconnect(self, close_code):
        # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
        if self.user_pk:
            logger.debug(
                "Disconnect user pk %s with close code %s", self.user_pk, close_code
            )
            # We only need to signal disconnect for an actual user
            if self.enable_connection_signals:
                self.dispatch_close(close_code)
        else:
            logger.debug("Disconnect was from anon, close code %s", close_code)

    # NOTE! database_sync_to_async doesn't work in tests - use mock to override
    @database_sync_to_async
    def get_token_user(self, key: str) -> Optional[AbstractUser]:
        with suppress(ObjectDoesNotExist):
            return Token.objects.get(key=key).user
        return None

    # NOTE! database_sync_to_async doesn't work in tests - use mock to override
    async def refresh_user(self) -> Optional[AbstractUser]:
        user = await get_user(self.scope)
        if user.pk is not None:
            self.user = user
            return user

    def get_language(self) -> str:
        """
        Get language according to this order:

        1) From cookie
        2) From Accept-Language HTTP header
        3) Default language from settings
        """
        # Note: This whole method should mimic the behaviour of Django's get_language_from_request
        # for consistency. So yeah this code looks like this in Django.
        lang_code = self.scope.get("cookies", {}).get(settings.LANGUAGE_COOKIE_NAME)

        if (
            lang_code is not None
            and lang_code in get_languages()
            and check_for_language(lang_code)
        ):
            return lang_code

        try:
            return get_supported_language_variant(lang_code)
        except LookupError:
            pass

        accept = []
        for (k, v) in self.scope.get("headers", {}):
            if k == b"accept-language":
                accept.append(v.decode())
            elif k == "accept-language":
                # Mostly for testing or in case this changes
                accept.append(v)
        if accept:
            accept_str = ",".join(accept)
            for accept_lang, unused in parse_accept_lang_header(accept_str):
                if accept_lang == "*":
                    break

                if not language_code_re.search(accept_lang):
                    continue

                try:
                    return get_supported_language_variant(accept_lang)
                except LookupError:
                    continue

        try:
            return get_supported_language_variant(settings.LANGUAGE_CODE)
        except LookupError:
            return settings.LANGUAGE_CODE

    async def handle_message(
        self, message: Union[AsyncRunnable, DeferredJob], require_action: bool = True
    ):
        """
        :param message: Outgoing or incoming message
        :param require_action: Cause an exception of the message wasn't acted upon.
        :return:
        """
        # FIXME: How do we handle errors here?
        activate(self.user_lang)  # FIXME: Every time...?
        act = 0
        if isinstance(message, AsyncRunnable):
            await message.run(self)
            act += 1
        if isinstance(message, DeferredJob):
            await message.pre_queue(self)
            queue = self.get_queue(message)
            message.enqueue(queue=queue)
            act += 1
        if not act and require_action:
            # This shouldn't be caught since it's a programming error
            raise TypeError(
                f"{message} must be an instance of either {AsyncRunnable} or {DeferredJob}"
            )

    async def receive(self, text_data: str = None, bytes_data=None):
        """ Receive from websocket """
        if text_data is None:
            # Connection will die
            raise ValueError(
                "Only text data accepted"
            )  # Maybe another exception or catch this?
        # Basic json load
        try:
            base_payload = json.loads(text_data)
        except json.decoder.JSONDecodeError:
            if settings.DEBUG:
                print(f"Invalid json: {text_data}")
            self.message_errors += 1
            self.last_error = now()
            return await self.post_error()
        # Should we allow this to be set per message?
        base_payload["l"] = self.user_lang
        # Wrap in message envelope
        try:
            envelope = IncomingEnvelope(**base_payload)
        except ValidationError as exc:
            message_id = base_payload.get("i", None)
            err = ValidationErrorMsg.create(message_id=message_id, errors=exc.errors())
            await self.send_error(err)
            self.message_errors += 1
            return await self.post_error()
        # Valid enough to mark as something incoming anyway
        self.last_recv = now()
        # Validate the payload
        try:
            message = BaseIncomingMessage.from_consumer(self, envelope)
        except ValidationError as exc:
            err = ValidationErrorMsg.create(message_id=envelope.i, errors=exc.errors())
            await self.send_error(err)
            # Don't store error count of these kind of errors
            return await self.post_error()
        # And do the actual handling of the message
        # other errors are probably the cause of a programming error so they should cause crashes.
        try:
            await self.handle_message(message)
        except BaseError as err:
            await self.send_error(err)
            await self.post_error()

    async def websocket_send(self, event: Dict):
        """Push data to the websocket. Any channels message with the type "websocket.send" will end up here.
        But don't use this method directly,
        send messages that are registered within registries.outgoing_messages
        """
        inc_p = event.get("p", None)
        if inc_p and isinstance(inc_p, str):
            event["p"] = json.loads(inc_p)
        envelope = OutgoingEnvelope(**event)
        message = BaseOutgoingMessage.from_consumer(self, envelope)
        await self.handle_message(message, require_action=False)
        payload = envelope.json(exclude={"type"})
        logger.debug("%s sent: %s", self.channel_name, payload)
        # Send message to WebSocket
        await self.send(text_data=payload)
        self.last_sent = now()

    async def post_error(self):
        """Things that might need to be cleaned up or handled after an incoming message has caused an error."""
        if self.message_errors > 10:
            logger.debug(
                "Consumer %s caused too many errors, disconnecting", self.channel_name
            )
            await self.close(1007)

    async def internal_receive(self, event: Dict):
        """
        Handle incoming internal messages.
        Incoming messages are dicts corresponding to InternalEnvelope.
        """
        inc_p = event.get("p", None)
        if inc_p and isinstance(inc_p, str):
            event["p"] = json.loads(inc_p)
        envelope = InternalEnvelope(**event)
        # This may cause validation errors, but that message shouldn't exist in that case it was resent from
        # backend and not from the user.
        # Crash and burn is okay here...
        if envelope.incoming:
            message = BaseIncomingMessage.from_consumer(self, envelope)
        else:
            message = BaseOutgoingMessage.from_consumer(self, envelope)
        await self.handle_message(message)

    async def send_error(self, error: BaseError):
        """Send an error directly to the consumer instead of going through the channels layer.

        Any error occurring within the consumer should be handled this way.
        """
        self.last_error = now()
        assert isinstance(error, BaseError)
        envelope = OutgoingEnvelope(
            p=error.data, i=error.mm.message_id, t=error.mm.type, s=error.FAILED
        )
        payload = envelope.json()
        logger.debug("Error sent: %s", payload)
        await self.send(text_data=payload)

    def dispatch_connect(self):
        """The connect signal even will be fired in a worker instead,
        since the sync calls to db aren't great to mix with async code.
        Currently channels testing doesn't work very well with database_sync_to_async. (2020-12 /Robin)
        """
        queue = self.get_queue(DEFAULT_QUEUE)
        return queue.enqueue(
            signal_websocket_connect,
            user_pk=self.user_pk,
            consumer_name=self.channel_name,
            language=self.user_lang,
        )

    def dispatch_close(self, close_code):
        """Ask as worker to signal instead of doing it here."""
        queue = self.get_queue(DEFAULT_QUEUE)
        return queue.enqueue(
            signal_websocket_close,
            user_pk=self.user_pk,
            consumer_name=self.channel_name,
            close_code=close_code,
            language=self.user_lang,
        )

    def get_queue(self, item: Union[str, DeferredJob]):
        if isinstance(item, str):
            return get_queue(name=item)
        elif isinstance(item, DeferredJob):
            return get_queue(name=item.queue)
        raise TypeError("Must be queue name as string or DeferredJob")

    def mark_subscribed(self, subscription: ChannelSubscription):
        self.protected_subscriptions[subscription.channel_name] = subscription

    def mark_left(self, subscription: ChannelSubscription):
        self.protected_subscriptions.pop(subscription.channel_name, None)
