from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _


User = get_user_model()


class Connection(models.Model):
    """ These are created on websocket connect, and marked as online=False when client disconnects.
        Since channels doesn't handle any kind of cleanup, it's important to check these now and then.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_connections"
    )
    # device_id = models.CharField(max_lenght=100)
    channel_name = models.CharField(
        verbose_name=_("Consumers own channel name"), max_length=100
    )
    online = models.BooleanField(default=True)
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


# class Subscription(models.Model):
#     """ Keep track of subscriptions for this connection. When deleted, make sure connections are cleaned up.
#     """
#     connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="connections")
#     channel_name = models.CharField(verbose_name=_("Channel name for the group subscription"), max_length=150)
#     # This may need channel layer too
#
#     class Meta:
#         unique_together = (("connection", "channel_name"),)
#
#     def cleanup(self):
#         pass
