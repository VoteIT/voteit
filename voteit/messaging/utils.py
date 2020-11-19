from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from voteit.messaging.models import Connection

logger = getLogger(__name__)

if TYPE_CHECKING:
    from voteit.core.component import Registry


def get_channel_registry() -> Registry:
    from voteit.messaging.registries import channel_registry
    return channel_registry


def update_user_status(user, channel_name, online=True):
    """ This is sync code so don't call this in any async context!
    """
    conn, created = Connection.objects.get_or_create(user=user, channel_name=channel_name)
    conn.online=online
    conn.save()
    return conn
