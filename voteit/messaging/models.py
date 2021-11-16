from __future__ import annotations
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class Connection(models.Model):
    """
    These are created on websocket connect, and marked as online=False when client disconnects.
    Since channels doesn't handle any kind of cleanup, it's important to check these now and then.
    """

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_connections",
    )
    # device_id = models.CharField(max_lenght=100)
    channel_name: str = models.CharField(
        verbose_name=_("Consumers own channel name"), max_length=100
    )
    # Is this considered to be online?
    online: bool = models.BooleanField(default=True)
    # Did this connection disappear without closing properly?
    awol: bool = models.BooleanField(default=False)
    # IP?
    first_seen = models.DateTimeField(
        auto_now_add=True, verbose_name=_("When the connection was made")
    )
    # Note that last_action is not done automatically, so this is an estimate
    last_action = models.DateTimeField(
        auto_now=True, verbose_name=_("Last recorded action of this consumer.")
    )
    last_query = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_(
            "Last time we sent a message to the consumer to check if it's online."
        ),
    )

    class Meta:
        unique_together = (("user", "channel_name"),)

    # Annotations
    objects: models.Manager


# FIXME Cleanup of channels should preferably be handled by the same iface as channels uses
# class Subscription(models.Model):
#     """ Keep track of object subscriptions for this connection.
#
#     """
#     connection: Connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="subscriptions")
#     obj_pk: int = models.IntegerField(verbose_name=_("PK of the object the channel type is for"))
#     channel_type: str = models.CharField(verbose_name=_("Channel type"), max_length=20)
#     # This may need channel layer too
#
#     class Meta:
#         unique_together = (("connection", "obj_pk", "channel_type"),)
#
#     def get_channel(self) -> Optional[AbstractObjectChannel]:
#         cr = get_channel_registry()
#         if self.channel_type in cr:
#             ch_type = cr[self.channel_type]
#             if issubclass(ch_type, AbstractObjectChannel):
#                 return ch_type.from_pk(self.obj_pk, consumer_channel=self.connection.channel_name)
#         return None
