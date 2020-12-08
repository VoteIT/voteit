from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Connection(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_connections",
    )
    # device_id = models.CharField(max_lenght=100)
    channel_name = models.CharField(verbose_name=_("Consumers own channel name"), max_length=100)
    online = models.BooleanField(
        default=True
    )
    # IP?
    first_seen = models.DateTimeField(auto_now_add=True)
    last_action = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("user", "channel_name"),)


# FIXME:
# class Subscription(models.Model):
#     """ Keep track of subscriptions for this connection. When deleted, make sure connections are cleaned up.
#     """
#     connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="connections")
#     channel_name = models.CharField(verbose_name=_("Channel name for the subscription"), max_length=150)
#
#     class Meta:
#         unique_together = (("connection", "channel_name"),)
#
# @
