"""Closing sockets from the server.

Its own module rather than part of ``utils.py`` for two reasons. The obvious
one is imports: ``channels.py`` imports ``utils.py``, so ``utils.py`` cannot
import ``user_group`` back. The important one is that the close itself does not
go through ``utils.publish()`` at all.

``s.close`` is not registered with ``@outgoing`` -- see the docstring on
``messages.py`` -- and with ``VOTEIT_WS_FAST_FANOUT`` on (the default)
``utils._send_now`` takes the passthrough route, which forwards the raw frame
to the browser and never invokes an event handler. A client that received
``{"action": "s.close"}`` would simply ignore it and stay connected. So every
close goes through chanx's typed event dispatcher instead, which is what
actually runs ``VoteitConsumer.close_connection``.

That also means these sends are immediate rather than deferred to commit by
``TransactionBatcher``, which is what we want: a close must not be batched or
reordered behind object updates.

The close frame carries nothing but a code. Anything the user should read is an
``s.msg`` (``voteit.core.messages.notice``), which every function here will
send first if given one -- to the same target, so the notice cannot arrive
after the socket has gone.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings

from voteit.core.messages.notice import Notice
from voteit.messaging.channels import session_group
from voteit.messaging.channels import user_group
from voteit.messaging.messages import CloseConnection
from voteit.messaging.models import GOING_AWAY
from voteit.messaging.models import NORMAL_CLOSURE
from voteit.messaging.models import Connection
from voteit.messaging.utils import Target
from voteit.messaging.utils import publish


def _dispatch(event: CloseConnection, *, group: str = "", channel: str = "") -> None:
    """Hand one close event to the channel layer. The single chokepoint.

    Exactly one of ``group`` or ``channel`` is used, mirroring
    ``utils.Target.group``. Tests patch this.
    """
    from voteit.messaging.consumer import VoteitConsumer

    if group:
        VoteitConsumer.broadcast_event_sync(event, group)
    else:
        VoteitConsumer.send_event_sync(event, channel)


def _close(
    *,
    group: str = "",
    channel: str = "",
    code: int,
    flush_session: bool = False,
    notice: Notice | None = None,
) -> None:
    if notice is not None:
        # on_commit=False on purpose: the close below is immediate, so a
        # batched notice would be flushed after the socket had already gone.
        publish(notice, Target(group or channel, group=bool(group)), on_commit=False)
    _dispatch(
        CloseConnection(payload={"code": code, "flush_session": flush_session}),
        group=group,
        channel=channel,
    )


def close_session_connections(
    session_key: str,
    *,
    code: int = NORMAL_CLOSURE,
    notice: Notice | None = None,
) -> None:
    """Close the sockets opened by one Django session.

    What an ordinary logout wants: the tabs that actually lost their login, and
    not the same user's other browser or phone, whose session is still valid.
    A logout passes ``code=LOGGED_OUT`` (4000) and no notice -- the code is the
    whole message, and the client words it.
    """
    _close(group=session_group(session_key), code=code, notice=notice)


def close_user_connections(
    user_pk: int,
    *,
    code: int = NORMAL_CLOSURE,
    flush_session: bool = False,
    notice: Notice | None = None,
) -> None:
    """Close every socket this user has open, on every device.

    With ``flush_session`` each consumer deletes its own session on the way
    out. That is the only way to reach a session we cannot name from here --
    see ``voteit.core.sessions`` for the other half of "log out everywhere".
    A logout everywhere passes ``code=LOGGED_OUT_EVERYWHERE`` (4001), the
    all-devices counterpart of the 4000 above.
    """
    _close(
        group=user_group(user_pk),
        code=code,
        flush_session=flush_session,
        notice=notice,
    )


def _online_channel_names() -> list[str]:
    """The address of every socket that currently looks online.

    Rows that are open but silent are left out -- they are almost always
    sockets that died with their process, so sending to them is a write to a
    queue nobody reads. For counting these rather than closing them, see
    ``voteit.messaging.presence``.
    """
    within = timedelta(seconds=getattr(settings, "VOTEIT_CONNECTION_STALE_AFTER", 900))
    return list(
        Connection.objects.online(within).values_list("channel_name", flat=True)
    )


def close_all_connections(
    *,
    code: int = GOING_AWAY,
    notice: Notice | None = None,
) -> list[str]:
    """Close every socket that currently looks online. Returns their names.

    One send per socket: there is no group holding all of them, and adding one
    would cost every connection an extra ``group_add`` for the sake of a
    command that runs at deploy time. ``Connection.channel_name`` is a
    channel-layer address, so this reaches sockets in other processes.
    """
    channel_names = _online_channel_names()
    for channel_name in channel_names:
        _close(channel=channel_name, code=code, notice=notice)
    return channel_names
