from logging import getLogger

from django.contrib.auth import get_user_model
from django_rq import job
from typing import List
from django.utils.translation import gettext as _

from voteit.core.queues import DEFAULT_QUEUE
from voteit.messaging.registries import websocket_incoming_messages
from voteit.messaging.signals import client_connect, client_close
from voteit.messaging.utils import update_user_status

logger = getLogger(__name__)

User = get_user_model()


# Queued from consumer, so no decorator!
def handle_job_message(msg_type, msg_data):
    """ """
    # Die here on validation errors - everything should already be validated
    #
    message = websocket_incoming_messages[msg_type](**msg_data)
    # FIXME catch errors and do handling here
    message.job()


@job(DEFAULT_QUEUE, timeout=5)
def signal_websocket_connect(user_pk: int = None, consumer_name: str = ""):
    user = User.objects.filter(pk=user_pk).first()
    logger.debug("%s connected consumer %s", user_pk, consumer_name)
    update_user_status(user, channel_name=consumer_name, online=True)
    client_connect.send(
        sender=None, user=user, user_pk=user_pk, consumer_name=consumer_name
    )


@job(DEFAULT_QUEUE, timeout=5)
def signal_websocket_close(
    user_pk: int = None, consumer_name: str = "", close_code: int = None
):
    user = User.objects.filter(pk=user_pk).first()
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
    )
    if user_pk:
        update_user_status(user, channel_name=consumer_name, online=False)
