"""Protocol messages: subscription control and connection housekeeping.

Deliberately not registered with @outgoing -- these are not object updates and
must not get generated .batch siblings. The consumer picks them up from its
handler signatures instead.
"""

from __future__ import annotations

from typing import Literal

from chanx.messages.base import BaseMessage
from pydantic import BaseModel
from pydantic import ConfigDict


class ChannelRef(BaseModel):
    """Identifies a channel: its type name plus the object's pk."""

    model_config = ConfigDict(frozen=True)

    pk: int
    channel_type: str


class SubscribedPayload(ChannelRef):
    channel_name: str


class ChannelSubscribe(BaseMessage):
    action: Literal["channel.subscribe"] = "channel.subscribe"
    payload: ChannelRef


class ChannelSubscribed(BaseMessage):
    """Subscription accepted. Initial state follows, then state_complete."""

    action: Literal["channel.subscribed"] = "channel.subscribed"
    payload: SubscribedPayload


class ChannelStateComplete(BaseMessage):
    """Every initial-state message for this channel has now been sent."""

    action: Literal["channel.state_complete"] = "channel.state_complete"
    payload: SubscribedPayload


class ChannelSubscribeError(BaseMessage):
    class Payload(ChannelRef):
        detail: str = ""

    action: Literal["channel.subscribe_error"] = "channel.subscribe_error"
    payload: Payload


class ChannelLeave(BaseMessage):
    action: Literal["channel.leave"] = "channel.leave"
    payload: ChannelRef


class ChannelLeft(BaseMessage):
    """Left a channel, either on request or because access was lost."""

    action: Literal["channel.left"] = "channel.left"
    payload: SubscribedPayload


class ChannelListSubscriptions(BaseMessage):
    action: Literal["channel.list_subscriptions"] = "channel.list_subscriptions"
    payload: None = None


class ChannelSubscriptions(BaseMessage):
    class Payload(BaseModel):
        subscriptions: list[ChannelRef] = []

    action: Literal["channel.subscriptions"] = "channel.subscriptions"
    payload: Payload


class RecheckSubscriptions(BaseMessage):
    """Internal: re-evaluate this user's subscriptions after a role change."""

    action: Literal["channel.recheck"] = "channel.recheck"
    payload: None = None


class Ping(BaseMessage):
    action: Literal["s.ping"] = "s.ping"
    payload: None = None


class Pong(BaseMessage):
    action: Literal["s.pong"] = "s.pong"
    payload: None = None


class ClosePayload(BaseModel):
    code: int = 1000


class CloseConnection(BaseMessage):
    """Internal: ask a consumer to close, e.g. when the user logs out."""

    action: Literal["s.close"] = "s.close"
    payload: ClosePayload = ClosePayload()


class ClosingConnection(BaseMessage):
    action: Literal["s.closing"] = "s.closing"
    payload: ClosePayload
