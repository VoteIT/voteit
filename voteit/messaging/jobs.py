from logging import getLogger

from django.contrib.auth import get_user_model
from django.db import transaction
from django_rq import job
from typing import Dict

from voteit.core.queues import DEFAULT_QUEUE
from voteit.messaging.abcs import DeferredJob, BaseError

# from voteit.messaging.signals import client_connect, client_close
# from voteit.messaging.utils import update_user_status
from voteit.messaging.utils import update_user_status

logger = getLogger(__name__)

User = get_user_model()


@job(DEFAULT_QUEUE, timeout=30)
def run_job(msg_data: Dict, mm_data: Dict, incoming=True, atomic=True):

    instance = DeferredJob.from_job(msg_data, mm_data, incoming=incoming)
    if instance.user is not None and instance.mm.consumer_name is not None:
        # Since this action is regarding this user connection, we're assuming we can update here
        # We don't know if the user is online still though
        update_user_status(instance.user, instance.mm.consumer_name, online=None)
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


# @job(DEFAULT_QUEUE, timeout=50)
# def signal_websocket_connect(user_pk: int = None, consumer_name: str = ""):
#     user = User.objects.filter(pk=user_pk).first()
#     logger.debug("%s connected consumer %s", user_pk, consumer_name)
#     update_user_status(user, channel_name=consumer_name, online=True)
#     client_connect.send(
#         sender=None, user=user, user_pk=user_pk, consumer_name=consumer_name
#     )
#
#
# @job(DEFAULT_QUEUE, timeout=5)
# def signal_websocket_close(
#     user_pk: int = None, consumer_name: str = "", close_code: int = None
# ):
#     user = User.objects.filter(pk=user_pk).first()
#     logger.debug(
#         "%s disconnected consumer %s. close_code: %s",
#         user_pk,
#         consumer_name,
#         close_code,
#     )
#     client_close.send(
#         sender=None,
#         user=user,
#         user_pk=user_pk,
#         consumer_name=consumer_name,
#         close_code=close_code,
#     )
#     if user_pk:
#         update_user_status(user, channel_name=consumer_name, online=False)
