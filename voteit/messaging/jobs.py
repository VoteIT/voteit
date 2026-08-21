"""Background jobs for the websocket layer.

Building a channel's initial state means running every collector registered
for that channel, each of which hits the database, so it stays off the event
loop -- as it did under envelope's DeferredJob. The consumer only enqueues; the
worker streams the result straight back to that one consumer.

``close_stale_connections`` is unrelated to subscribing: it is the periodic
tidy-up for the Connection table, which nothing else ever reaps.
"""

from __future__ import annotations

from datetime import timedelta
from logging import getLogger

import django_rq
from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.transaction import get_connection
from django.utils.timezone import now
from django.utils.translation import activate

from voteit.core import RQ_DEFAULT_QUEUE
from voteit.core.decorators import schedule_job
from voteit.messaging.bundle import iter_bundles
from voteit.messaging.messages import ChannelLeft
from voteit.messaging.messages import ChannelStateComplete
from voteit.messaging.messages import ChannelSubscribed
from voteit.messaging.messages import ChannelSubscribeError
from voteit.messaging.models import ABNORMAL_CLOSURE
from voteit.messaging.models import Connection
from voteit.messaging.registry import collectors_for
from voteit.messaging.registry import context_channel_registry
from voteit.messaging.state import AppState
from voteit.messaging.utils import send_to_consumer

logger = getLogger(__name__)

# Subscribing is interactive: if it has not run almost immediately it is not
# worth running at all.
SUBSCRIBE_TTL = 20
SUBSCRIBE_TIMEOUT = 20


def enqueue_subscribe(
    *, user_pk: int, consumer_channel: str, channel_type: str, pk: int, language: str
):
    return django_rq.get_queue(RQ_DEFAULT_QUEUE).enqueue(
        subscribe_job,
        user_pk=user_pk,
        consumer_channel=consumer_channel,
        channel_type=channel_type,
        pk=pk,
        language=language,
        ttl=SUBSCRIBE_TTL,
        job_timeout=SUBSCRIBE_TIMEOUT,
    )


def enqueue_recheck(*, user_pk: int, consumer_channel: str, subscriptions: list[dict]):
    return django_rq.get_queue(RQ_DEFAULT_QUEUE).enqueue(
        recheck_job,
        user_pk=user_pk,
        consumer_channel=consumer_channel,
        subscriptions=subscriptions,
        ttl=SUBSCRIBE_TTL,
        job_timeout=SUBSCRIBE_TIMEOUT,
    )


def _send(message, consumer_channel: str) -> None:
    """Send a protocol message through chanx's typed event dispatcher.

    Not the cheaper passthrough that ``_send_state`` uses: ``on_subscribed``
    and ``on_left`` maintain the consumer's own ``channel_subs`` set, and those
    handlers only run on this path.
    """
    from voteit.messaging.consumer import VoteitConsumer

    VoteitConsumer.send_event_sync(message, consumer_channel)


def _send_state(message, consumer_channel: str) -> None:
    """Send a state bundle the cheap way: serialise once, forward verbatim.

    ``on_state_bundle`` is a pure passthrough, so nothing is lost by skipping
    chanx's dispatcher -- and two things are gained. A bundle is up to a
    megabyte of deeply nested models, and the typed path would re-validate all
    of it on the consumer's event loop. Worse, ``handle_channel_event``
    swallows a ValidationError with nothing but a log line, so any drift in the
    payload union would make the entire initial state vanish silently.

    Ordering against ``_send`` holds: Channels awaits both handlers inline on
    the same consumer, in channel-layer order.
    """
    send_to_consumer(message, consumer_channel, on_commit=False)


def _applicable(collector) -> bool:
    """Whether this collector wants to run, tolerating a broken guess."""
    try:
        return collector.applicable()
    except Exception:
        if get_connection().needs_rollback:
            raise
        logger.exception(
            "applicable() failed for app state collector %r", collector.name
        )
        return False


def _collect(collector, app_state: AppState) -> None:
    """Run one collector, keeping a failure inside its own section.

    A collector that raises marks its section ``failed`` and the rest still
    run, so one broken app no longer costs the client its entire initial state.
    The exception is a database error: it leaves the atomic block unusable and
    there is no savepoint to roll back to -- taking one per collector would
    cost an extra round trip each, which is most of what this rework set out to
    save.
    """
    with app_state.section(collector.name) as section:
        try:
            collector.collect(app_state)
        except Exception:
            if get_connection().needs_rollback:
                raise
            section.failed = True
            logger.exception("App state collector %r failed", collector.name)


def subscribe_job(
    *,
    user_pk: int,
    consumer_channel: str,
    channel_type: str,
    pk: int,
    language: str | None = None,
) -> None:
    """Check permission, join the group, then stream the initial state.

    The client receives channel.subscribed -- carrying the names of every
    collector that will contribute -- then one or more channel.state bundles,
    then channel.state_complete. An ordinary meeting fits in a single bundle.
    """
    activate(language or settings.LANGUAGE_CODE)
    channel_cls = context_channel_registry[channel_type]
    channel = channel_cls(pk, consumer_channel=consumer_channel)
    user = get_user_model().objects.filter(pk=user_pk).first()

    # durable=True so every collector sees one consistent snapshot, matching
    # what envelope's DeferredJob.atomic did.
    with transaction.atomic(durable=True):
        try:
            allowed = channel.allow_subscribe(user)
        except ObjectDoesNotExist:
            allowed = False
        if not allowed:
            _send(
                ChannelSubscribeError(
                    payload={
                        "pk": pk,
                        "channel_type": channel_type,
                        "detail": "Not allowed to subscribe",
                    }
                ),
                consumer_channel,
            )
            return

        async_to_sync(channel.subscribe)()
        ref = {
            "pk": pk,
            "channel_type": channel_type,
            "channel_name": channel.channel_name,
        }

        # Settled before anything is sent, so the client is told up front
        # exactly which sections to expect and never waits on a collector that
        # opted out.
        collectors = [
            collector
            for collector in (cls(channel, user) for cls in collectors_for(channel_cls))
            if _applicable(collector)
        ]
        _send(
            ChannelSubscribed(
                payload={**ref, "collectors": [c.name for c in collectors]}
            ),
            consumer_channel,
        )

        app_state = AppState()
        for collector in collectors:
            _collect(collector, app_state)

        for bundle in iter_bundles(
            app_state.sections, pk=pk, channel_type=channel_type
        ):
            _send_state(bundle, consumer_channel)

        _send(ChannelStateComplete(payload=ref), consumer_channel)


def recheck_job(
    *, user_pk: int, consumer_channel: str, subscriptions: list[dict]
) -> None:
    """Drop any subscription the user may no longer have access to."""
    user = get_user_model().objects.filter(pk=user_pk).first()
    for ref in subscriptions:
        channel_cls = context_channel_registry.get(ref["channel_type"])
        if channel_cls is None:
            continue
        channel = channel_cls(ref["pk"], consumer_channel=consumer_channel)
        try:
            allowed = user is not None and channel.allow_subscribe(user)
        except ObjectDoesNotExist:
            allowed = False
        if allowed:
            continue
        async_to_sync(channel.leave)()
        _send(
            ChannelLeft(
                payload={
                    "pk": ref["pk"],
                    "channel_type": ref["channel_type"],
                    "channel_name": channel.channel_name,
                }
            ),
            consumer_channel,
        )


@schedule_job("*/30 * * * *")
def close_stale_connections() -> int:
    """Write a close code onto connections whose socket vanished without one.

    Nothing else reaps this table. A consumer killed with its process never
    reaches ``websocket_disconnect``, so its row keeps ``code IS NULL`` forever
    and stays in the ``conn_open_last_action_idx`` partial index that every
    "who is online" query depends on.

    Closing such a row changes no visible number: it is already outside the
    window ``ConnectionQuerySet.online()`` uses, so it was never counted as
    present. And if the socket does turn out to be alive, its next inbound
    message sets ``code`` back to NULL via ``update_connection``.

    The window is deliberately far wider than ``VOTEIT_CONNECTION_UPDATE_INTERVAL``
    so an ordinary quiet stretch never trips it.
    """
    window = timedelta(seconds=settings.VOTEIT_CONNECTION_STALE_JOB_AFTER)
    closed = Connection.objects.stale(window).update(code=ABNORMAL_CLOSURE)
    if closed:
        logger.info("Closed %s stale connection(s)", closed)
    purged = purge_old_connections()
    if purged:
        logger.info("Purged %s closed connection(s)", purged)
    return closed


def purge_old_connections() -> int:
    """Delete long-closed rows, if a retention window is configured.

    Off unless ``VOTEIT_CONNECTION_RETENTION_DAYS`` is set. Safe to enable --
    voteit.stats.HistoryLog already holds the daily aggregates these rows feed
    -- but opting in is the operator's call, not an upgrade side effect.
    """
    days = getattr(settings, "VOTEIT_CONNECTION_RETENTION_DAYS", None)
    if not days:
        return 0
    deleted, _ = Connection.objects.filter(
        code__isnull=False, last_action__lt=now() - timedelta(days=days)
    ).delete()
    return deleted
