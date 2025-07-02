from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from logging import getLogger
from typing import TYPE_CHECKING, Iterator

from django.db import models
from pydantic.main import BaseModel

from voteit.core.abcs import ABCModel

if TYPE_CHECKING:
    from voteit.speaker.models import Speaker
    from voteit.speaker.models import SpeakerList
    from voteit.speaker.models import SpeakerListSystem

logger = getLogger(__name__)


class SpeakerSystemContext(ABCModel):
    @property
    @abstractmethod
    def speaker_system(self) -> SpeakerListSystem:
        """
        Return the speaker_system object. It could be a ForeignKey relation or something that gets the object.
        """

    class Meta:
        abstract = True


class ListMethod(ABC):
    settings_schema: type[BaseModel] | None = None

    def __init__(self, speaker_system: SpeakerListSystem):
        self.speaker_system = speaker_system

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique name for method
        """

    @property
    @abstractmethod
    def title(self) -> str:
        """
        Human-readable title
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable explanation of what this does.
        """

    @abstractmethod
    def reorder(
        self, safe_speakers: list[Speaker], incoming_order: list[Speaker]
    ) -> Iterator[Speaker]:
        """
        Override this method to implement actual quotas or similar.
        The default one simply orders users according to the order they entered the list.

        Handle within an atomic transaction.
        """

    def get_queryset(self, speaker_list: SpeakerList) -> models.QuerySet[Speaker]:
        """
        Return a queryset suitable for the reorder method.
        """
        return speaker_list.speakers_in_queue_or_speaking()
