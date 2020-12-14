from __future__ import annotations

from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import AbstractUser
from django.utils.timezone import now
from voteit.messaging.models import Connection
from voteit.messaging.signals import connection_terminated

logger = getLogger(__name__)

if TYPE_CHECKING:
    from voteit.core.component import Registry
    from django.db.models import QuerySet


def get_channel_registry() -> Registry:
    from voteit.messaging.registries import channel_registry

    return channel_registry


def get_incoming_registry() -> Registry:
    from voteit.messaging.registries import incoming_messages

    return incoming_messages


def get_outgoing_registry() -> Registry:
    from voteit.messaging.registries import outgoing_messages

    return outgoing_messages


def update_connection_status(
    user: AbstractUser,
    channel_name: str,
    online: Optional[bool] = True,
    awol: Optional[bool] = None,
) -> Connection:
    """ This is sync code so don't call this in any async context!
    """
    conn, created = Connection.objects.get_or_create(
        user=user, channel_name=channel_name
    )
    send_signal = False
    if online is not None:  # We might not know
        if conn.online == True and online == False:
            send_signal = True
        conn.online = online
    if awol is not None:
        conn.awol = awol
    conn.save()
    if send_signal:
        connection_terminated.send(sender=Connection, connection=conn, awol=conn.awol)
    return conn


def cleanup_connection_status(secs=180, only_user: Optional[AbstractUser] = None):
    """ Check connections marked as active and make sure they're still active. """
    # Note: This assumes channels_redis backend
    since = now() - timedelta(seconds=secs)
    query = dict(online=True, last_action__lt=since)
    if only_user:
        query["user"] = only_user
    qs = Connection.objects.filter(**query)
    channel_names = set(qs.values_list("channel_name", flat=True))
    found = async_to_sync(check_redis_keys)(channel_names)
    to_remove = channel_names - found
    if to_remove:
        # logger.debug("Changing connection status of %s objects", len(to_remove))
        qs = Connection.objects.filter(online=True, channel_name__in=to_remove)
        logger.debug("Changing connection status of %s objects", qs.count())
        for conn in qs:
            conn.online = False
            conn.awol = True
            connection_terminated.send(
                sender=Connection, connection=conn, awol=conn.awol
            )
            conn.save()
    else:
        logger.debug("No expired connections found")


def get_old_connections(hours=24) -> QuerySet:
    """ Get old connection items, suitable for dumping somewhere else or simply deleting. """
    since = now() - timedelta(hours=hours)
    return Connection.objects.filter(online=False, last_action__lt=since)


def cleanup_old_connections(hours=24):
    """ Delete connection info from db.
        It might be a good idea to store some of the information before deleting. """
    qs = get_old_connections(hours)
    qs.delete()


async def check_redis_keys(keys) -> set:
    """ Return a set of keys that exist. For instance the consumer channel name.
    """
    channel_layer = get_channel_layer()
    found = set()
    # FIXME: There's no stable API to get a sensible connection index from the pool in channel layer right now :(
    async with channel_layer.connection(0) as connection:
        for k in keys:
            if await connection.exists(k):
                found.add(k)
    return found
