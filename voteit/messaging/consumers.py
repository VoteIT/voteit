import json
from logging import getLogger
from typing import TYPE_CHECKING, Optional

from channels.auth import get_user
from channels.exceptions import DenyConnection
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from pydantic import ValidationError

from voteit.messaging.exceptions import UnsupportedMessageType
from voteit.messaging.jobs import signal_websocket_connect
from voteit.messaging.jobs import signal_websocket_close
from voteit.messaging.messages import IncomingPayload
from voteit.messaging.messages import OutgoingErrorMessage
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

    async def connect(self):
        connection_token = self.scope["url_route"]["kwargs"]["connection_token"]
        # FIXME: Check connection token against storage. Redis, db?
        await self.refresh_user()
        self.user_pk = (
            self.user.pk
        )  # Save for later use in case of invalidation of the user object
        logger.debug(
            "Connection for user: %s with token '%s'", self.user, connection_token
        )
        if not isinstance(self.user, AbstractUser):
            logger.debug("Anonymous user kicked")
            raise DenyConnection()
        if connection_token == "invalid":  # FIXME: Just for testing
            logger.debug("Invalid token, closing connection")
            raise DenyConnection()
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

    async def refresh_user(self):
        self.user = await get_user(self.scope)

    async def receive(self, text_data:str=None, bytes_data=None):
        """ Receive from websocket """
        # FIXME: A lot of error checking...
        incoming = None
        accept_message = False
        # base_payload = {}
        message = None
        try:
            if text_data is None:
                raise UnsupportedMessageType("Only text data accepted")
            incoming = IncomingPayload.parse_raw(text_data)
            try:
                msg_type = websocket_incoming_messages[incoming.t]
            except KeyError:
                raise UnsupportedMessageType(
                    f"t was not one of {websocket_incoming_messages.keys()}"
                )
            #  FIXME: Not all sent data might be consumed, for instance if there's a typo on the incoming key of
            #  something that isn't required. That data will silently be thrown away.
            #  Do we want it to be logged or error in that case?

            if incoming.p:
                payload = json.loads(incoming.p)
            else:
                payload = {}
            message = msg_type(**payload)
            accept_message = True
        except json.decoder.JSONDecodeError:
            if getattr(settings, "ECHO_WS_ERRORS", None):
                await self.send_error("Invalid json")
            if settings.DEBUG:
                print(f"Invalid json, either payload {text_data}")
            self.message_errors += 1
        except ValidationError as exc:
            message_id = incoming and incoming.i or None
            if getattr(settings, "ECHO_WS_ERRORS", None):
                await self.send_error(exc.errors(), message_id=message_id)
            if settings.DEBUG:
                print(f"Incoming message {message_id} payload error: {exc.errors()}")
        #         raise
            self.message_errors += 1
        except UnsupportedMessageType:
            logger.debug(f"t was not one of {websocket_incoming_messages.keys()}")
            self.message_errors += 1
        finally:
            if self.message_errors > 10:
                await self.close(1007)
        if incoming is not None and message is not None and accept_message:
            logger.debug("Incoming: %s / %s", incoming.t, incoming.i)
            # Errors here too...? This is an application error in that case
            await message.consume(self, message_id=incoming.i)

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
        payload = json.loads(event["p"])
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
    ):
        """
        Send error to websocket
        FIXME: TBD!

        :param message: Human readable error
        :param message_id: Attach message id trace if this was caused by an incoming message
        :param err_type: Type of error
        :return:
        """
        err_msg = OutgoingErrorMessage(
            t=err_type, i=message_id, p={"message": message}
        )
        await self.send(text_data=err_msg.json())
