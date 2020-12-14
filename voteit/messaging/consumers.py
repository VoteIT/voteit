import json
from contextlib import suppress
from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING, Optional, Dict, Union

from channels.auth import get_user
from channels.db import database_sync_to_async
from channels.exceptions import DenyConnection
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now
from pydantic import ValidationError
from rest_framework.authtoken.models import Token

from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.envelopes import IncomingEnvelope
from voteit.messaging.envelopes import InternalEnvelope
from voteit.messaging.envelopes import OutgoingEnvelope
from voteit.messaging.exceptions import UnsupportedMessageType
from voteit.messaging.errors import BaseError
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.registries import incoming_messages
from voteit.messaging.signals import client_connect, client_close
from voteit.messaging.utils import update_connection_status

logger = getLogger(__name__)

if TYPE_CHECKING:
    pass


User = get_user_model()

# FIXME: We might need to check if channels properly cleans up groups
# They could fill up with messages fast in case no one is there to receive them.
# All clients won't send close signal, since they might just loose connection or go away for another reason.
# FIXME: Test full channels

# FIXME: Query consumer for last action
# FIXME Store subscriptions


class WebsocketDemuxConsumer(AsyncWebsocketConsumer):
    """ Demultiplexing consumer.
    """

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
    # For testing injection
    message_registry = incoming_messages
    # Last sent
    last_sent: datetime
    last_recv: datetime

    async def connect(self):
        connection_token = self.scope["url_route"]["kwargs"]["connection_token"]
        self.user = await self.get_token_user(key=connection_token)
        if self.user is None:
            # FIXME: get_user ie refresh_user is the correct way to go
            # When using session auth instead of token:
            await self.refresh_user()
        if self.user is None:
            logger.debug("Invalid token, closing connection")
            raise DenyConnection()
        # Save for later use in case of invalidation of the user object
        self.user_pk = self.user.pk
        # And mark action
        self.last_sent = self.last_recv = now()
        logger.debug(
            "Connection for user: %s with token '%s'", self.user, connection_token
        )
        await self.accept()
        logger.debug("Connection accepted for user %s (%s)", self.user, self.user.pk)
        # This is sync code, so if we need to add lots of stuff here move this to a job

        await self.signal_connect()

    async def disconnect(self, close_code):
        # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
        if self.user_pk:
            logger.debug(
                "Disconnect user pk %s with close code %s", self.user_pk, close_code
            )
            # We only need to signal disconnect for an actual user
            await self.signal_disconnect(close_code)
        else:
            logger.debug("Disconnect was from anon, close code %s", close_code)
        # This is sync code, so if we need to add lots of stuff here move this to a job

    @database_sync_to_async
    def get_token_user(self, key: str) -> Optional[AbstractUser]:
        with suppress(ObjectDoesNotExist):
            return Token.objects.get(key=key).user
        return None

    async def refresh_user(self):
        user = await get_user(self.scope)
        if user.pk is not None:
            self.user = user

    async def handle_message(self, message: Union[AsyncRunnable, DeferredJob]):
        # FIXME: How do we handle errors here?
        act = 0
        if isinstance(message, AsyncRunnable):
            await message.run(self)
            act += 1
        if isinstance(message, DeferredJob):
            await message.pre_queue(self)
            message.enqueue()
            act += 1
        if not act:
            # This shuldn't be caught since it's a programming errors
            raise TypeError(
                f"{message} must be an instance of either {AsyncRunnable} or {DeferredJob}"
            )

    async def receive(self, text_data: str = None, bytes_data=None):
        """ Receive from websocket """
        if text_data is None:
            # Connection will die
            raise UnsupportedMessageType("Only text data accepted")
        # Basic json load
        try:
            base_payload = json.loads(text_data)
        except json.decoder.JSONDecodeError:
            if settings.DEBUG:
                print(f"Invalid json, either payload {text_data}")
            self.message_errors += 1
            return await self.post_error()
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
        """ Push data to the websocket. Any channels message with the type "websocket.send" will end up here.
            But don't use this method directly,
            send messages that are registered within registries.outgoing_messages
        """
        message = OutgoingEnvelope(**event)
        payload = message.json(exclude={"type"})
        logger.debug("%s sent: %s", self.channel_name, payload)
        self.last_sent = now()
        # Send message to WebSocket
        await self.send(text_data=payload)

    async def post_error(self):
        """ Things that might need to be cleaned up or handled after an incoming message has caused an error.
        """
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
        envelope = InternalEnvelope(**event)
        # This may cause validation errors, but that message shouldn't exist in that case it was resent from
        # backend and not from the user.
        # Crash and burn is okay here...
        message = BaseIncomingMessage.from_consumer(self, envelope)
        await self.handle_message(message)

    async def send_error(self, error: BaseError):
        """ Send an error directly to the consumer instead of going through the channels layer.

            Any error occurring within the consumer should be handled this way.
        """
        assert isinstance(error, BaseError)
        envelope = OutgoingEnvelope(
            p=error.data, i=error.mm.message_id, t=error.mm.type, s=error.FAILED
        )
        payload = envelope.json()
        logger.debug("Error sent: %s", payload)
        await self.send(text_data=payload)

    @database_sync_to_async
    def signal_connect(self):
        conn = None
        if self.user is not None:
            conn = update_connection_status(self.user, channel_name=self.channel_name, online=True)
        client_connect.send(
            sender=None,
            user=self.user,
            user_pk=self.user_pk,
            consumer_name=self.channel_name,
            connection=conn,
        )

    @database_sync_to_async
    def signal_disconnect(self, close_code: int):
        if self.user is None or self.user.pk != self.user_pk:
            user = User.objects.get(pk=self.user_pk)
        else:
            user = self.user
        conn = None
        if user is not None:
            conn = update_connection_status(user, channel_name=self.channel_name, online=False)
        client_close.send(
            sender=None,
            user=user,
            user_pk=self.user_pk,
            consumer_name=self.channel_name,
            close_code=close_code,
            connection=conn,
        )
