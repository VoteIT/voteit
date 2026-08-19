from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils.timezone import now


class ConnectionQuerySet(models.QuerySet):
    def open(self):
        """Connections that have not reported a close code yet."""
        return self.filter(code__isnull=True)

    def active_since(self, timestamp: datetime):
        return self.filter(last_action__gt=timestamp)

    def online(self, within: timedelta):
        """Open connections that did something within the given window.

        Channels never tells us about connections that vanish without closing,
        so an open connection is only evidence of presence if it has been
        active recently.
        """
        return self.open().active_since(now() - within)

    def user_ids(self):
        """For use as a subquery: ``.filter(pk__in=...user_ids())``."""
        return self.values("user_id")


class Connection(models.Model):
    """A single websocket connection.

    Created when a consumer connects and updated -- throttled -- as it sends
    messages, so ``last_action`` is an estimate rather than exact. ``code`` is
    the websocket close code and is null while the connection is open, so
    "currently online" is ``code__isnull=True``.

    Note there is no foreign key to the user: rows outlive the connection they
    describe and are read in bulk by the stats jobs, so they are deliberately
    decoupled from user deletion.
    """

    user_id: int = models.PositiveBigIntegerField()
    channel_name: str = models.CharField(max_length=150)
    connected_at: datetime = models.DateTimeField(default=now, blank=True)
    last_action: datetime = models.DateTimeField(default=now, blank=True)
    code: int | None = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-last_action",)
        indexes = [
            # Stats and the active-user purge look connections up by user.
            # The envelope model got this for free from its unique_together.
            models.Index(fields=["user_id"], name="conn_user_id_idx"),
            # "seen recently", regardless of whether the socket is still open.
            models.Index(fields=["last_action"], name="conn_last_action_idx"),
            # "currently online" -- by far the hottest query, and a partial
            # index keeps it small since most rows are long-closed.
            models.Index(
                fields=["last_action"],
                condition=Q(code__isnull=True),
                name="conn_open_last_action_idx",
            ),
        ]

    objects = ConnectionQuerySet.as_manager()

    def __str__(self):
        state = "open" if self.code is None else f"closed ({self.code})"
        return f"Connection {self.channel_name} for user {self.user_id} [{state}]"
