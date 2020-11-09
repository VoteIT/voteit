from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.dispatch import receiver

from voteit.messaging.channels.abcs import AbstractObjectChannel
from voteit.messaging.registries import channel_registry
from voteit.messaging.signals import client_connect, client_close

if TYPE_CHECKING:
    pass

logger = getLogger(__name__)


@channel_registry("user")
class UserChannel(AbstractObjectChannel):
    Model = get_user_model()

    @property
    def channel_name(self):
        return f"user_{self.pk}"

    def allow_publish(self, user):
        return user.pk == self.pk

    def allow_subscribe(self, user):
        return user.pk == self.pk


@receiver(client_connect)
def subscribe_client_to_users_channel(user:AbstractUser, consumer_name:str, user_pk:int, **kw):
    user_channel = UserChannel.from_instance(user, consumer_channel=consumer_name)
    user_channel.sync_subscribe()


@receiver(client_close)
def cleanup_users_channel(user:Optional[AbstractUser], consumer_name:str, user_pk:int, close_code:Optional[int], **kw):
    """ Cleanup will probably be after the user object has been removed from the consumer,
        so don't trust the user arg here!
    """
    user_channel = UserChannel.from_pk(user_pk, consumer_channel=consumer_name)
    user_channel.sync_leave()
