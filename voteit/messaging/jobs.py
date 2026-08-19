"""Background jobs behind channel.subscribe and channel.recheck.

Building a channel's initial state means running every ``channel_subscribed``
receiver, each of which hits the database, so it stays off the event loop --
as it did under envelope's DeferredJob. The consumer only enqueues; the worker
streams the result straight back to that one consumer.
"""

from __future__ import annotations

from logging import getLogger

import django_rq
from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils.translation import activate

from voteit.core import RQ_DEFAULT_QUEUE
from voteit.messaging.messages import ChannelLeft
from voteit.messaging.messages import ChannelStateComplete
from voteit.messaging.messages import ChannelSubscribed
from voteit.messaging.messages import ChannelSubscribeError
from voteit.messaging.registry import context_channel_registry
from voteit.messaging.signals import channel_subscribed
from voteit.messaging.state import AppState

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
    from voteit.messaging.consumer import VoteitConsumer

    VoteitConsumer.send_event_sync(message, consumer_channel)


def subscribe_job(
    *,
    user_pk: int,
    consumer_channel: str,
    channel_type: str,
    pk: int,
    language: str | None = None,
) -> None:
    """Check permission, join the group, then stream the initial state.

    The client receives channel.subscribed, then one message per contributing
    receiver -- usually a batch -- then channel.state_complete.
    """
    activate(language or settings.LANGUAGE_CODE)
    channel_cls = context_channel_registry[channel_type]
    channel = channel_cls(pk, consumer_channel=consumer_channel)
    user = get_user_model().objects.filter(pk=user_pk).first()

    # durable=True so every receiver sees one consistent snapshot, matching
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
        _send(ChannelSubscribed(payload=ref), consumer_channel)

        app_state = AppState()
        channel_subscribed.send(
            sender=channel_cls,
            context=channel.context,
            user=user,
            app_state=app_state,
        )
        for message in app_state:
            _send(message, consumer_channel)

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
