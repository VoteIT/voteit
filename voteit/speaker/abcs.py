from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from datetime import timedelta
from logging import getLogger
from random import shuffle
from typing import TYPE_CHECKING

from django.utils.timezone import now
from pydantic.main import BaseModel

from voteit.core.abcs import ABCModel

if TYPE_CHECKING:
    from voteit.speaker.models import SpeakerListSystem
    from voteit.speaker.models import SpeakerList
    from django.contrib.auth.models import AbstractUser


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

    def shuffle(self, speaker_list: SpeakerList) -> list[int]:
        """
        Shuffle order - should always be handled within an atomic transaction + the speaker list locked!
        It fetches speaker objects and updates them rather than using the cached speaker_list.order.

        The reason for this somewhat odd solution: Keep order even when other methods may reorder later on.
        """
        speakers = list(speaker_list.speakers_in_queue())
        shuffle(speakers)
        new_created_base = now() - timedelta(seconds=len(speakers))
        for i, speaker in enumerate(speakers, 1):
            speaker.created = new_created_base + timedelta(seconds=i)
            speaker.save()
        return [x.user_id for x in speakers]  # For testing, not used

    @abstractmethod
    def reorder(self, speaker_list: SpeakerList) -> list[int]:
        """
        Override this method to implement actual quotas or similar.
        The default one simply orders users according to the order they entered the list.

        This method returns the primary keys of the users according to the new order.
        Make sure to include the safe speakers!

        Handle within an atomic transaction.
        """
