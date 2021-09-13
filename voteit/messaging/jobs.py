from logging import getLogger
from typing import Dict
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import activate
from django_rq import job
from voteit.core.queues import DEFAULT_QUEUE
from voteit.messaging.abcs import BaseError
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.signals import client_close
from voteit.messaging.signals import client_connect
from voteit.messaging.utils import update_connection_status

logger = getLogger(__name__)
User = get_user_model()


def _set_lang(lang=None):
    """
    Language is set via the request normally, so it has to be set manually outside of the regular request scope.
    """
    if lang is None:
        lang = settings.LANGUAGE_CODE
    activate(lang)


@job(DEFAULT_QUEUE, timeout=30)
def run_job(msg_data: Dict, mm_data: Dict, incoming=True, atomic=True):
    """This is the job that handles all DeferredJob messages.
    They're dispatched from the message consumer.
    """
    instance = DeferredJob.from_job(msg_data, mm_data, incoming=incoming)
    if instance.user is not None and instance.mm.consumer_name is not None:
        # Since this action is regarding this user connection, we're assuming we can update here
        # We don't know if the user is online still though
        update_connection_status(instance.user, instance.mm.consumer_name, online=None)
    _set_lang(instance.mm.language)
    try:
        if atomic:
            with transaction.atomic():
                instance.run_job()
        else:
            instance.run_job()
    except BaseError as err:  # Catchable, nice errors
        # Attach other things to error in case they aren't there
        if err.mm.message_id is None:
            err.mm.message_id = instance.mm.message_id
        err.send_outgoing(instance.mm.consumer_name)


@job(DEFAULT_QUEUE, timeout=5)
def signal_websocket_connect(
    user_pk: int = None, consumer_name: str = "", language: Optional[str] = None
):
    """ This job handles the sync code for a user connecting to a consumer. """
    user = User.objects.get(
        pk=user_pk
    )  # User should always exist when this job is dispatched
    _set_lang(language)
    logger.debug("%s connected consumer %s", user_pk, consumer_name)
    conn = update_connection_status(user=user, channel_name=consumer_name, online=True)
    client_connect.send(
        sender=None,
        user=user,
        consumer_name=consumer_name,
        connection=conn,
    )


@job(DEFAULT_QUEUE, timeout=5)
def signal_websocket_close(
    user_pk: int = None,
    consumer_name: str = "",
    close_code: int = None,
    language: Optional[str] = None,
):

    user = User.objects.get(
        pk=user_pk
    )  # User should always exist when this job is dispatched
    _set_lang(language)
    conn = update_connection_status(user, channel_name=consumer_name, online=False)
    logger.debug(
        "%s disconnected consumer %s. close_code: %s",
        user_pk,
        consumer_name,
        close_code,
    )
    client_close.send(
        sender=None,
        user=user,
        user_pk=user_pk,
        consumer_name=consumer_name,
        close_code=close_code,
        connection=conn,
    )
