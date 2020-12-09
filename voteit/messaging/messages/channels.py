from __future__ import annotations

from pydantic import validator, BaseModel
from typing import TYPE_CHECKING
from django.utils.translation import gettext as _

from voteit.messaging.abcs import DeferredJob, MessageABC, BaseOutgoingMessage, BaseIncomingMessage
from voteit.messaging.errors import UnauthorizedError, NotFoundError
from voteit.messaging.registries import incoming_messages
from voteit.messaging.registries import outgoing_messages
from voteit.messaging.utils import get_channel_registry

if TYPE_CHECKING:
    from voteit.messaging.abcs import AbstractObjectChannel


SUBSCRIBE = "channel.subscribe"
LEAVE = "channel.leave"

SUBSCRIBED = "channel.subscribed"
LEFT = "channel.left"


class ChannelSchema(BaseModel):
    pk: int
    channel_type: str

    @validator("channel_type")
    def real_channel_type(cls, v):
        cr = get_channel_registry()
        v = v.lower()
        if v not in cr:
            raise ValueError(f"'{v}' is not a valid channel")
        return v


class BaseChannelCommand(BaseIncomingMessage):
    def get_channel(
        self, channel_type: str, pk: int, consumer_name: str
    ) -> AbstractObjectChannel:
        cr = get_channel_registry()
        # This may cause errors right?
        return cr[channel_type](pk, consumer_name)


@incoming_messages
class Subscribe(BaseChannelCommand, DeferredJob):
    name = SUBSCRIBE
    schema = ChannelSchema
    data: ChannelSchema

    def run_job(self):
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        if channel.allow_subscribe(self.user):
            channel.subscribe()
            msg = Subscribed.from_message(self)
            msg.send_outgoing(self.mm.consumer_name, success=True)
        else:
            raise UnauthorizedError.from_message(
                self,
                permission=channel.permission,
                msg=_("You're not allowed to subscribe to this channel"),
            )


@incoming_messages
class Leave(BaseChannelCommand, DeferredJob):
    name = LEAVE
    schema = ChannelSchema
    data: ChannelSchema

    def run_job(self):
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        if channel.context is None:
            raise NotFoundError.from_message(
                self,
                msg=_("Context doesn't exist"),
            )
        if channel.allow_leave(self.user):
            channel.subscribe()
            msg = Left.from_message(self)
            msg.send_outgoing(self.mm.consumer_name, success=True)
        else:
            raise UnauthorizedError.from_message(
                self,
                permission=channel.permission,
                msg=_("You're not allowed to leave to this channel"),  # Hotel California...
            )


@outgoing_messages
class Subscribed(BaseOutgoingMessage):
    name = SUBSCRIBED


@outgoing_messages
class Left(BaseOutgoingMessage):
    name = LEFT
