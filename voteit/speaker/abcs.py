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

    def get_spoken_count(
        self, speaker_list: SpeakerList, user: AbstractUser | int
    ) -> int:
        if not isinstance(user, int):
            user = user.pk
        return speaker_list.speaker_items.filter(
            seconds__isnull=False, user_id=user
        ).count()

    def shuffle(self, speaker_list: SpeakerList) -> list[int]:
        """
        Shuffle order - should always be handled within an atomic transaction.
        It fetches speaker objects rather than usign the cached speaker_list.order
        """
        speaker_qs = speaker_list.speakers_in_queue()
        new_order = list(
            speaker_list.speakers_in_queue().values_list("user_id", flat=True)
        )
        shuffle(new_order)
        new_created_base = now() - timedelta(seconds=len(new_order))
        for i, speaker in enumerate(
            sorted(speaker_qs, key=lambda x: new_order.index(x.user_id)), 1
        ):
            speaker.created = new_created_base + timedelta(seconds=i)
            speaker.save()
        return new_order

    def reorder(self, speaker_list: SpeakerList) -> list[int]:
        """
        Override this method to implement actual quotas or similar.
        The default one simply orders users according to the order they entered the list.

        This method returns the primary keys of the users according to the new order.
        Make sure to include the safe speakers!

        Handle within an atomic transaction.
        """
        resorted_queue = speaker_list.get_user_pk_in_queue_created_order()
        if speaker_list.speaker_system.safe_positions:
            safe_in_queue = speaker_list.order_list[
                : speaker_list.speaker_system.safe_positions
            ]
            for pk in reversed(safe_in_queue):
                if pk in resorted_queue:
                    resorted_queue.remove(pk)
                    resorted_queue.insert(0, pk)
        return resorted_queue
