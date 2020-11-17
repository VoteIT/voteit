from logging import getLogger

from django.contrib.auth import get_user_model
from django_rq import job
from voteit.messaging.signals import client_connect, client_close

logger = getLogger(__name__)

User = get_user_model()


def _get_user(pk):
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
