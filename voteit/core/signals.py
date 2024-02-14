from __future__ import annotations

from os import getenv
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db.models.signals import class_prepared
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver
from async_signals import receiver as areceiver
from envelope.async_signals import consumer_connected
from envelope.app.online_channel.channel import OnlineChannel

from voteit.core import models_to_register

if TYPE_CHECKING:
    from django.db.models import Model
    from envelope.consumers.websocket import WebsocketConsumer


# The following signals will provide arguments "sender", "instance" and "roles"
roles_added = Signal()
roles_removed = Signal()


@receiver(class_prepared)
def deferred_register_model(sender: Model, **kw):
    """Prep register models in content registry.
    Done in apps ready()
    """

    models_to_register.add(sender)


@areceiver(consumer_connected)
async def send_frontend_version(*, consumer: WebsocketConsumer, **kwargs):
    if consumer.channel_name:
        if FRONTEND_VERSION := getenv("FRONTEND_VERSION"):
            from voteit.core.messages.frontend_version import FrontendVersion

            msg = FrontendVersion(version=FRONTEND_VERSION)
            await consumer.send_ws_message(msg)


def post_init_registrations():
    User = get_user_model()
    from voteit.core.messages.user import InvalidateUserCache

    @receiver(pre_delete, sender=User)
    @receiver(post_save, sender=User)
    def invalidate_user_cache(*, instance: User, created=False, **kwargs):
        if not created:
            msg = InvalidateUserCache(pk=instance.pk)
            OnlineChannel().sync_publish(msg)
