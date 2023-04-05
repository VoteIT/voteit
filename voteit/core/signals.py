from __future__ import annotations

from os import getenv
from typing import TYPE_CHECKING

from django.db.models.signals import class_prepared
from django.dispatch import Signal
from django.dispatch import receiver

from envelope.signals import client_connect
from envelope.utils import websocket_send
from voteit.core import models_to_register

if TYPE_CHECKING:
    from django.db.models import Model


# The following signals will provide arguments "sender", "instance" and "roles"
roles_added = Signal()
roles_removed = Signal()


@receiver(class_prepared)
def deferred_register_model(sender: Model, **kw):
    """Prep register models in content registry.
    Done in apps ready()
    """

    models_to_register.add(sender)


@receiver(client_connect)
def send_frontend_version(consumer_name=None, **kwargs):
    if consumer_name:
        if FRONTEND_VERSION := getenv("FRONTEND_VERSION"):
            from voteit.core.messages.frontend_version import FrontendVersion

            msg = FrontendVersion(version=FRONTEND_VERSION)
            websocket_send(msg, channel_name=consumer_name, on_commit=False)
