import json
from contextlib import suppress
from logging import getLogger
from typing import TYPE_CHECKING, Optional, List

from channels.auth import get_user
from channels.db import database_sync_to_async
from channels.exceptions import DenyConnection
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django_rq import get_queue
from pydantic import ValidationError
from rest_framework.authtoken.models import Token

from voteit.messaging.exceptions import UnsupportedMessageType
from voteit.messaging.jobs import signal_websocket_connect
from voteit.messaging.jobs import signal_websocket_close
from voteit.messaging.messages import IncomingPayload, MsgState
from voteit.messaging.messages import OutgoingErrorMessage
from voteit.messaging.messages.abcs import AbstractJobMessage
from voteit.messaging.messages import MessageContext
from voteit.messaging.registries import internal_messages
from voteit.messaging.registries import websocket_incoming_messages

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
    message_registry = websocket_incoming_messages

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

    async def receive(self, text_data: str = None, bytes_data=None):
        """ Receive from websocket """
        # FIXME: A lot of error checking...
        incoming = None
        accept_message = False
        base_payload = {}
        message = None
        try:
            if text_data is None:
                raise UnsupportedMessageType("Only text data accepted")
            base_payload = json.loads(text_data)
            incoming = IncomingPayload(**base_payload)
            try:
                msg_type = self.message_registry[incoming.t]
            except KeyError:
                raise UnsupportedMessageType(
                    f"t was not one of {self.message_registry.keys()}"
                )
            #  FIXME: Not all sent data might be consumed, for instance if there's a typo on the incoming key of
            #  something that isn't required. That data will silently be thrown away.
            #  Do we want it to be logged or error in that case?
            payload = incoming.p or {}
            mc = MessageContext(
                consumer_name=self.channel_name,
                message_id=incoming.i,
                user_pk=self.user_pk,
                type=incoming.t,
            )
            message = msg_type(mc=mc, **payload)
            accept_message = True
        except json.decoder.JSONDecodeError:
            await self.send_error("Invalid json", err_type="error.json")
            if settings.DEBUG:
                print(f"Invalid json, either payload {text_data}")
            self.message_errors += 1
        except ValidationError as exc:
            message_id = base_payload.get("i", None)
            await self.send_error(
                "Validation fail", message_id=message_id, errors=exc.errors()
            )
            if settings.DEBUG:
                print(f"Incoming message {message_id} payload error: {exc.errors()}")
        except UnsupportedMessageType:
            message_id = base_payload.get("i", None)
            logger.debug(f"t was not one of {self.message_registry.keys()}")
            await self.send_error(
                "Unsupported message type",
                message_id=message_id,
                err_type="error.message_type",
            )
            self.message_errors += 1
        finally:
            if self.message_errors > 10:
                await self.close(1007)
        if incoming is not None and message is not None and accept_message:
            logger.debug("Consuming incoming: %s / %s", incoming.t, incoming.i)
            await message.consume(self)
            # Errors here too...? This is an application error in that case
        else:
            pass
            #  FIXME: log error?

    async def websocket_send(self, event):
        """ Push data to the websocket. Any channels message with the type "websocket.send" will end up here.
            But don't use this method directly,
            send messages that are registered within registries.websocket_outgoing_messages
        """
        print(f"{self.channel_name} sent: {event}")
        payload = event["payload"]
        # Send message to WebSocket
        await self.send(text_data=payload)

    async def internal_receive(self, event):
        """ Receive internal messages with the type internal.receive
            Event should be:
            {"type": INTERNAL_MESSAGE, "payload": self.json(), "t": mtype, "i": message_id},

            See AbstractInternalMessage

        """
        # print(f"Internal message: {event}")
        try:
            msg_type = internal_messages[event["t"]]
        except KeyError:
            logger.debug(f"t was not one of {internal_messages.keys()}")
            raise
        payload = event["p"]
        message_id = event["i"]
        try:
            message = msg_type(**payload)
        except ValidationError as exc:
            if settings.DEBUG:
                print(f"Message {message_id} payload error: {exc.errors()}")
            else:
                raise
            return
        logger.debug("Internal: %s / %s", event["t"], message_id)

        await message.consume(self, message_id=message_id)  # Errors here too...?

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
