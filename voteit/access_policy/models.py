from __future__ import annotations

from abc import abstractmethod
from logging import getLogger
from typing import TYPE_CHECKING

from django.db import models

from voteit.core.abcs import MeetingContext

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting

logger = getLogger(__name__)


class AccessPolicy(MeetingContext):
    """
    Subclass this to create an access policy.

    The tests for this class are in voteit.access_policy.app.automatic
    """

    active: bool = models.BooleanField(default=False)
    meeting: Meeting = models.OneToOneField(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s",
    )
    exporters = {"meeting": {}}
    importers = {"meeting": {}, "organisation": {}}

    class Meta:
        abstract = True

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Name of access policy, used as ID.
        """

    @property
    @abstractmethod
    def title(self) -> str:
        """
        Human-readable name
        """

    def __str__(self):
        return f"{self.__class__.__name__} for meeting {self.meeting.pk}"
