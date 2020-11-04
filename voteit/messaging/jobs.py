from logging import getLogger

from django.contrib.auth import get_user_model
from django_rq import job
from typing import Optional
from voteit.messaging.signals import client_connect, client_close
from voteit.messaging.utils import get_channel_registry

logger = getLogger(__name__)


def _get_user(pk):
    User = get_user_model()
    return User.objects.filter(pk=pk).first()


@job("default", timeout=5)
def signal_websocket_connect(user_pk: int = None, consumer_name: str = ""):
    user = _get_user(user_pk)
    logger.debug("%s connected consumer %s", user_pk, consumer_name)
    client_connect.send(sender=None, user=user, user_pk=user_pk, consumer_name=consumer_name)


@job("default", timeout=5)
def signal_websocket_close(
    user_pk: int = None, consumer_name: str = "", close_code: int = None
):
    user = _get_user(user_pk)
    logger.debug("%s disconnected consumer %s. close_code: %s", user_pk, consumer_name, close_code)
    client_close.send(sender=None, user=user, user_pk=user_pk, consumer_name=consumer_name, close_code=close_code)


@job("default", timeout=500)
def subscribe(user_pk: int, channel_type: str, consumer_name: str, pk: int, message_id:Optional[int]=None):
    user = _get_user(user_pk)
    cr = get_channel_registry()
    channel_model = cr[channel_type]  # Should be validated already
    try:
        channel = channel_model.from_pk(pk, consumer_channel=consumer_name)
    except:
        #  FIXME Catch and send fail message
        raise
    if channel.allow_subscribe(user):
        channel.sync_subscribe(message_id=message_id)
    else:
        pass
        # FIXME: Send permission error


@job("default", timeout=5)
def leave(user_pk: int, channel_type: str, consumer_name: str, pk: int, message_id:Optional[int]=None):
    user = _get_user(user_pk)
    cr = get_channel_registry()
    channel_model = cr[channel_type]  # Should be validated already
    try:
        channel = channel_model.from_pk(pk, consumer_channel=consumer_name)
    except:
        #  FIXME Catch and send fail message
        raise
    if channel.allow_leave(user):
        channel.sync_leave(message_id=message_id)
    else:
        pass
        # FIXME: Send permission error
