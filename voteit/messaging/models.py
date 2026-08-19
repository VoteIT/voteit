from __future__ import annotations

from datetime import datetime

from django.db import models
from django.utils.timezone import now


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

    # Annotations
    objects: models.Manager

    def __str__(self):
        state = "open" if self.code is None else f"closed ({self.code})"
        return f"Connection {self.channel_name} for user {self.user_id} [{state}]"
