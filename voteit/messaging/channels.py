"""Publish/subscribe channels.

A channel is a channel-layer group plus, for context channels, the object and
permission that decide who may subscribe to it. Nine channels share one shape
-- (name, model, permission) -> group ``"<name>_<pk>"`` -- which is why
``channel.subscribe`` stays one generic handler backed by a registry rather
than a handler per domain.
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

from channels import DEFAULT_CHANNEL_LAYER
from channels.layers import get_channel_layer
from django.db import models
from django.utils.functional import cached_property

from voteit.messaging.registry import register_channel
from voteit.messaging.utils import Target
from voteit.messaging.utils import publish as _publish

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage


class PubSubChannel(ABC):
    """A channel-layer group messages can be published to."""

    layer_name = DEFAULT_CHANNEL_LAYER
    consumer_channel: str | None

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the channel type, not of a specific channel."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Channel-layer group name. Unique per channel."""

    def __init__(
        self, consumer_channel: str | None = None, *, layer_name: str | None = None
    ):
        self.consumer_channel = consumer_channel
        if layer_name:
            self.layer_name = layer_name

    @property
    def target(self) -> Target:
        return Target(self.channel_name, group=True, layer=self.layer_name)

    def sync_publish(self, message: BaseMessage, on_commit: bool = True) -> None:
        """Publish to everyone subscribed to this channel.

        Inside an atomic block with ``on_commit`` the send is deferred to
        commit, where runs of the same message type collapse into one batch.
        """
        _publish(message, self.target, on_commit=on_commit)

    async def subscribe(self) -> None:
        if not self.consumer_channel:  # pragma: no coverage
            raise ValueError("No consumer_channel specified")
        layer = get_channel_layer(self.layer_name)
        await layer.group_add(self.channel_name, self.consumer_channel)

    async def leave(self) -> None:
        assert self.consumer_channel
        layer = get_channel_layer(self.layer_name)
        await layer.group_discard(self.channel_name, self.consumer_channel)


class ContextChannel(PubSubChannel, ABC):
    """A channel about one specific object."""

    pk: int

    def __init__(
        self,
        pk: int,
        consumer_channel: str | None = None,
        *,
        layer_name: str | None = None,
    ):
        self.pk = pk
        super().__init__(consumer_channel=consumer_channel, layer_name=layer_name)

    @property
    def channel_name(self) -> str:
        return f"{self.name}_{self.pk}"

    @property
    @abstractmethod
    def model(self) -> type[models.Model]:
        """The model this channel is about."""

    @property
    @abstractmethod
    def permission(self) -> str | None:
        """Permission required to subscribe. None skips the check."""

    @classmethod
    def from_instance(
        cls,
        instance: models.Model,
        consumer_channel: str | None = None,
        *,
        layer_name: str | None = None,
    ) -> ContextChannel:
        assert isinstance(instance, cls.model), f"Instance must be a {cls.model}"
        inst = cls(
            instance.pk, consumer_channel=consumer_channel, layer_name=layer_name
        )
        # Set context straight away to avoid a lookup
        inst.context = instance
        return inst

    @cached_property
    def context(self) -> models.Model:
        """The object. Raises the model's DoesNotExist if it is gone."""
        return self.model.objects.get(pk=self.pk)

    def allow_subscribe(self, user) -> bool:
        if self.permission is None:
            return True
        if user is None:
            return False
        return user.has_perm(self.permission, self.context)


@register_channel
class UserChannel(ContextChannel):
    """A user's own channel. Only that user may subscribe."""

    name = "user"
    permission = None
    # ABCMeta resolves abstract attributes when the class object is created,
    # so this cannot be a classproperty calling get_user_model() -- the app
    # registry is not ready yet. MessagingConfig.ready() binds it instead.
    model = None

    def allow_subscribe(self, user) -> bool:
        return bool(user and user.pk and user.pk == self.pk)


def user_group(user_pk: int) -> str:
    return f"{UserChannel.name}_{user_pk}"
