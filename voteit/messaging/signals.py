from django.contrib.auth.models import AbstractUser
from django.dispatch import Signal, receiver
from voteit.messaging.utils import update_user_status


client_connect = Signal(providing_args=["consumer_name", "user", "user_pk"])
client_close = Signal(providing_args=["consumer_name", "user", "user_pk", "close_code"])


@receiver(client_connect)
def update_status_on_connect(user: AbstractUser, consumer_name: str, **kw):
    update_user_status(user, channel_name=consumer_name, online=True)


@receiver(client_close)
def update_status_on_disconnect(user: AbstractUser, consumer_name: str, **kw):
    update_user_status(user, channel_name=consumer_name, online=False)
