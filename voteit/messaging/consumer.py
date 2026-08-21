"""The single VoteIT websocket consumer.

The socket is push-only apart from subscription control and ping: every
app-level incoming message was migrated to REST (see CHANGELOG v0.47), so
there are no domain handlers here at all.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from os import getenv
from typing import TYPE_CHECKING
from typing import Any
from typing import MutableMapping

from asgiref.sync import sync_to_async
from chanx.channels.websocket import AsyncJsonWebsocketConsumer
from chanx.core.authenticator import BaseAuthenticator
from chanx.core.decorators import channel
from chanx.core.decorators import event_handler
from chanx.core.decorators import ws_handler
from chanx.core.websocket import ChanxWebsocketConsumerMixin
from django.conf import settings
from django.utils.module_loading import autodiscover_modules
from django.utils.timezone import now

from voteit.core.messages.version import VersionMessage
from voteit.messaging.bundle import bind_bundle_schema
from voteit.messaging.channels import ONLINE_GROUP
from voteit.messaging.channels import user_group
from voteit.messaging.jobs import enqueue_recheck
from voteit.messaging.jobs import enqueue_subscribe
from voteit.messaging.messages import AppStateBundle
from voteit.messaging.messages import ChannelLeave
from voteit.messaging.messages import ChannelLeft
from voteit.messaging.messages import ChannelListSubscriptions
from voteit.messaging.messages import ChannelRef
from voteit.messaging.messages import ChannelStateComplete
from voteit.messaging.messages import ChannelSubscribe
from voteit.messaging.messages import ChannelSubscribed
from voteit.messaging.messages import ChannelSubscribeError
from voteit.messaging.messages import ChannelSubscriptions
from voteit.messaging.messages import CloseConnection
from voteit.messaging.messages import ClosingConnection
from voteit.messaging.messages import Ping
from voteit.messaging.messages import Pong
from voteit.messaging.messages import RecheckSubscriptions
from voteit.messaging.models import ABNORMAL_CLOSURE
from voteit.messaging.models import Connection
from voteit.messaging.registry import all_outgoing_messages
from voteit.messaging.registry import context_channel_registry

if TYPE_CHECKING:
    from voteit.core.models import User

# passthrough_events is read when the class below is created, so every
# messages.py must already have run. MessagingConfig.ready() does this too;
# repeating it here keeps the consumer importable on its own.
autodiscover_modules("messages")
# Same reason: AppStateBundle's payload union is built from the registry that
# the line above just filled. Idempotent, so ready() calling it again is fine.
bind_bundle_schema()


class AuthenticatedUserAuthenticator(BaseAuthenticator):
    """Accept any logged-in user. Anonymous sockets are closed."""

    async def authenticate(self, scope: MutableMapping[str, Any]) -> bool:
        user = scope.get("user")
        return bool(user and user.is_authenticated)


class SubscriptionMixin(ChanxWebsocketConsumerMixin):
    """channel.subscribe / leave / list_subscriptions / recheck."""

    # Not `subscriptions`: chanx uses that name for its own topic registry.
    channel_subs: set[ChannelRef]

    # output_type is spelled out because chanx's AsyncAPI generator turns the
    # NoneType arm of a `X | None` return annotation into a dangling
    # `#/channels/voteit/messages/none_type` reference, which breaks /asyncapi/docs/.
    @ws_handler(
        summary="Subscribe to a context channel", output_type=ChannelSubscribeError
    )
    async def subscribe(
        self, message: ChannelSubscribe
    ) -> ChannelSubscribeError | None:
        ref = message.payload
        if ref.channel_type not in context_channel_registry:
            return ChannelSubscribeError(
                payload={**ref.model_dump(), "detail": "Unknown channel type"}
            )
        # Enqueueing talks to redis, so it must not block the event loop.
        await sync_to_async(enqueue_subscribe, thread_sensitive=False)(
            user_pk=self.user.pk,
            consumer_channel=self.channel_name,
            channel_type=ref.channel_type,
            pk=ref.pk,
            language=self.scope.get("language") or settings.LANGUAGE_CODE,
        )
        # The worker sends channel.subscribed, the state, then state_complete.
        return None

    @event_handler
    async def on_subscribed(self, event: ChannelSubscribed) -> ChannelSubscribed:
        self.channel_subs.add(
            ChannelRef(pk=event.payload.pk, channel_type=event.payload.channel_type)
        )
        return event

    @event_handler
    async def on_state_bundle(self, event: AppStateBundle) -> AppStateBundle:
        return event

    @event_handler
    async def on_state_complete(
        self, event: ChannelStateComplete
    ) -> ChannelStateComplete:
        return event

    @event_handler
    async def on_subscribe_error(
        self, event: ChannelSubscribeError
    ) -> ChannelSubscribeError:
        return event

    @event_handler
    async def on_left(self, event: ChannelLeft) -> ChannelLeft:
        self.channel_subs.discard(
            ChannelRef(pk=event.payload.pk, channel_type=event.payload.channel_type)
        )
        return event

    @ws_handler(summary="Leave a context channel")
    async def leave(self, message: ChannelLeave) -> ChannelLeft:
        ref = message.payload
        channel_cls = context_channel_registry.get(ref.channel_type)
        group = (
            channel_cls(ref.pk).channel_name
            if channel_cls
            else f"{ref.channel_type}_{ref.pk}"
        )
        await self.channel_layer.group_discard(group, self.channel_name)
        self.channel_subs.discard(ref)
        return ChannelLeft(payload={**ref.model_dump(), "channel_name": group})

    @ws_handler(summary="List current subscriptions")
    async def list_subscriptions(
        self, _message: ChannelListSubscriptions
    ) -> ChannelSubscriptions:
        return ChannelSubscriptions(
            payload={
                "subscriptions": sorted(
                    self.channel_subs, key=lambda r: (r.channel_type, r.pk)
                )
            }
        )

    @event_handler
    async def recheck(self, _event: RecheckSubscriptions) -> None:
        """Re-evaluate subscriptions, e.g. after the user's roles changed."""
        if not self.channel_subs:
            return None
        await sync_to_async(enqueue_recheck, thread_sensitive=False)(
            user_pk=self.user.pk,
            consumer_channel=self.channel_name,
            subscriptions=[ref.model_dump() for ref in self.channel_subs],
        )
        return None

    # output_type is spelled out because the warning goes out through
    # send_message rather than as a return value, and chanx builds the
    # outgoing union -- and /asyncapi/docs/ -- from handler annotations only.
    @event_handler(output_type=ClosingConnection)
    async def close_connection(self, event: CloseConnection) -> None:
        await self.send_message(ClosingConnection(payload=event.payload))
        await self.close(event.payload.code)
        return None


class ConnectionMixin(ChanxWebsocketConsumerMixin):
    """Keeps the Connection row roughly up to date.

    Writes are throttled, so last_action is an estimate. Done inline rather
    than on a queue: without an FK or a unique constraint these are a bare
    INSERT and a bare UPDATE.
    """

    last_connection_update: datetime
    connection_update_interval: int = getattr(
        settings, "VOTEIT_CONNECTION_UPDATE_INTERVAL", 60
    )

    @ws_handler(summary="Connectivity check")
    async def handle_ping(self, _message: Ping) -> Pong:
        return Pong()

    async def receive_message(self, message) -> None:
        await super().receive_message(message)
        await self.update_connection()

    async def websocket_disconnect(self, message: dict):
        # Fall back to 1006 rather than None: a disconnect message without a
        # code would otherwise write the row back as still open, leaving a
        # dangling connection behind a socket we know has gone.
        await self.update_connection(code=message.get("code") or ABNORMAL_CLOSURE)
        await super().websocket_disconnect(message)

    async def update_connection(self, code: int | None = None) -> None:
        user = self.scope.get("user")
        if not (user and user.pk):
            return
        stale = (
            self.last_connection_update
            + timedelta(seconds=self.connection_update_interval)
            < now()
        )
        if code is None and not stale:
            return
        self.last_connection_update = now()
        await Connection.objects.filter(
            user_id=user.pk, channel_name=self.channel_name
        ).aupdate(last_action=now(), code=code)


@channel(name="voteit")
class VoteitConsumer(
    SubscriptionMixin,
    ConnectionMixin,
    AsyncJsonWebsocketConsumer,
):
    authenticator_class = AuthenticatedUserAuthenticator
    log_ignored_actions = ["s.ping", "s.pong"]
    # Every outgoing type plus its .batch sibling. This is what populates
    # outgoing_message_adapter and the AsyncAPI schema.
    passthrough_events = all_outgoing_messages()

    user: User | None = None

    async def post_authentication(self) -> None:
        self.user = self.scope["user"]
        self.channel_subs = set()
        await self.channel_layer.group_add(user_group(self.user.pk), self.channel_name)
        await self.channel_layer.group_add(ONLINE_GROUP, self.channel_name)
        self.last_connection_update = now()
        await Connection.objects.acreate(
            user_id=self.user.pk, channel_name=self.channel_name
        )
        await self.send_message(
            VersionMessage(
                payload={
                    "backend": getenv("BACKEND_VERSION", ""),
                    "frontend": getenv("FRONTEND_VERSION", ""),
                }
            )
        )
