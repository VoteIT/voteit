import json
from contextlib import suppress
from logging import getLogger
from typing import TYPE_CHECKING, Optional, List, Dict, Union

from channels.auth import get_user
from channels.db import database_sync_to_async
from channels.exceptions import DenyConnection
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from pydantic import ValidationError
from rest_framework.authtoken.models import Token
from voteit.messaging.abcs import BaseIncomingMessage, DeferredJob, AsyncRunnable
from voteit.messaging.envelopes import (
    IncomingEnvelope,
    InternalEnvelope,
    OutgoingEnvelope,
)

from voteit.messaging.exceptions import UnsupportedMessageType
from voteit.messaging.jobs import signal_websocket_connect
from voteit.messaging.jobs import signal_websocket_close
from voteit.messaging.messages import IncomingPayload, MsgState
from voteit.messaging.messages import OutgoingErrorMessage
from voteit.messaging.registries import outgoing_messages
from voteit.messaging.registries import incoming_messages

logger = getLogger(__name__)

if TYPE_CHECKING:
    pass


# FIXME: We might need to check if channels properly cleans up groups
# They could fill up with messages fast in case no one is there to receive them.
# All clients won't send close signal, since they might just loose connection or go away for another reason.
# FIXME: Test full channels


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

    async def connect(self):
        connection_token = self.scope["url_route"]["kwargs"]["connection_token"]
        self.user = await database_sync_to_async(self.get_token_user)(
            key=connection_token
        )
        if (
            self.user is None
        ):  # FIXME: get_user ie refresh_user is the correct way to go
            await self.refresh_user()
        if self.user is None:
            logger.debug("Invalid token, closing connection")
            raise DenyConnection()
        # When using session auth instead of token:
        self.user_pk = (
            self.user.pk
        )  # Save for later use in case of invalidation of the user object
        logger.debug(
            "Connection for user: %s with token '%s'", self.user, connection_token
        )
        await self.accept()
        logger.debug("Connection accepted for user %s (%s)", self.user, self.user.pk)
        signal_websocket_connect.delay(
            user_pk=self.user_pk, consumer_name=self.channel_name
        )

    async def disconnect(self, close_code):
        # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
        if self.user_pk:
            logger.debug(
                "Disconnect user pk %s with close code %s", self.user_pk, close_code
            )
        else:
            logger.debug("Disconnect was from anon, close code %s", close_code)
        signal_websocket_close.delay(
            user_pk=self.user_pk, consumer_name=self.channel_name, close_code=close_code
        )

    def get_token_user(self, key: str) -> Optional[AbstractUser]:
        with suppress(ObjectDoesNotExist):
            return Token.objects.get(key=key).user
        return None

    async def refresh_user(self):
        self.user = await get_user(self.scope)

    async def handle_message(self, message: Union[AsyncRunnable, DeferredJob]):
        # FIXME: How do we handle errors here?
        act = 0
        if isinstance(message, AsyncRunnable):
            await message.run()
            act += 1
        if isinstance(message, DeferredJob):
            await message.pre_queue(self)
            message.enqueue()
            act += 1
        if not act:
            raise TypeError(
                f"{message} must be an instance of either {AsyncRunnable} or {DeferredJob}"
            )

    async def receive(self, text_data: str = None, bytes_data=None):
        """ Receive from websocket """
        if text_data is None:
            # Connection will die
            raise UnsupportedMessageType("Only text data accepted")
        try:
            base_payload = json.loads(text_data)
        except json.decoder.JSONDecodeError:
            await self.send_error("Invalid json", err_type="error.json")
            if settings.DEBUG:
                print(f"Invalid json, either payload {text_data}")
            self.message_errors += 1
            return await self.post_receive()
        try:
            envelope = IncomingEnvelope(**base_payload)
        except ValidationError as exc:
            await self.send_error(
                "Validation fail",
                message_id=base_payload.get("i", None),
                errors=exc.errors(),
            )
            self.message_errors += 1
            return await self.post_receive()
        message = BaseIncomingMessage.from_consumer(self, envelope)
        await self.handle_message(message)

    async def websocket_send(self, event: Dict):
        """ Push data to the websocket. Any channels message with the type "websocket.send" will end up here.
            But don't use this method directly,
            send messages that are registered within registries.websocket_outgoing_messages
        """
        message = OutgoingEnvelope(**event)
        payload = message.json(exclude={"type"})
        logger.debug("%s sent: %s", self.channel_name, payload)
        # Send message to WebSocket
        await self.send(text_data=payload)

    async def post_receive(self):
        logger.debug(
            "Consumer %s caused too many errors, disconnecting", self.channel_name
        )
        if self.message_errors > 10:
            await self.close(1007)

    async def internal_receive(self, event: Dict):
        """ Handle incoming internal messages. Incoming messages are dicts corresponding to InternalEnvelope. """
        envelope = InternalEnvelope(**event)
        message = BaseIncomingMessage.from_consumer(self, envelope)
        await self.handle_message(message)

    # async def _internal_receive(self, event):
    #     """ Receive internal messages with the type internal.receive
    #         Event should be:
    #         {"type": INTERNAL_MESSAGE, "payload": self.json(), "t": mtype, "i": message_id},
    #
    #         See AbstractInternalMessage
    #
    #     """
    #     # print(f"Internal message: {event}")
    #
    #     try:
    #         msg_type = internal_messages[event["t"]]
    #     except KeyError:
    #         logger.debug(f"t was not one of {internal_messages.keys()}")
    #         raise
    #     payload = event["p"]
    #     message_id = event["i"]
    #     try:
    #         message = msg_type(**payload)
    #     except ValidationError as exc:
    #         if settings.DEBUG:
    #             print(f"Message {message_id} payload error: {exc.errors()}")
    #         else:
    #             raise
    #         return
    #     logger.debug("Internal: %s / %s", event["t"], message_id)
    #
    #     await message.consume(self, message_id=message_id)  # Errors here too...?

    async def send_error(
        self,
        message: str,
        err_type: str = "error.unknown",
        message_id: Optional[str] = None,
        errors: List = [],
    ):
        """
        Send error to websocket
        FIXME: TBD!
        :param message: Human readable error
        :param message_id: Attach message id trace if this was caused by an incoming message
        :param err_type: Type of error
        :param errors: Error structure, if applicable.
        :return:
        """
        payload = {"message": message, "errors": errors}
        err_msg = OutgoingErrorMessage(
            t=err_type, i=message_id, p=payload, s=MsgState.FAILED
        )
        await self.send(text_data=err_msg.json())
