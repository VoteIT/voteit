from __future__ import annotations

from abc import abstractmethod, ABC
from datetime import timedelta
from logging import getLogger
from random import shuffle
from typing import TYPE_CHECKING, List, Optional

from django.db.models import Max
from django.utils.timezone import now
from pydantic.main import BaseModel


if TYPE_CHECKING:
    from voteit.speaker.models import SpeakerListSystem
    from voteit.speaker.models import SpeakerList

logger = getLogger(__name__)


class ListMethod(ABC):
    def __init__(self, speaker_system: SpeakerListSystem):
        self.speaker_system = speaker_system

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for method"""

    @property
    @abstractmethod
    def title(self) -> str:
        """Human-readable title"""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable explanation of what this does."""

    @property
    def settings_schema(self) -> Optional[BaseModel]:
        """
        Possible settings schema for this speaker list method.
        Will be enforced if it exists
        """
        return None

    def shuffle(self, speaker_list: SpeakerList) -> List[int]:
        """
        Shuffle order - should always be handled within an atomic transaction.
        """
        list_items = list(speaker_list.speaker_items.filter(order__isnull=False))
        shuffle(list_items)
        new_order = []
        new_created_base = now() - timedelta(seconds=len(list_items))
        for order, speaker in enumerate(list_items, 1):
            speaker.order = order
            speaker.created = new_created_base + timedelta(seconds=order)
            speaker.save()
            new_order.append(speaker.pk)
        return new_order

    def reorder(self, speaker_list: SpeakerList) -> List[int]:
        """
        Override this method to implement actual quotas or similar.
        The default one simply orders users according to the order they entered the list.

        This method returns the primary keys of the speakers according to the new order.
        Make sure to include the safe speakers!

        Handle within an atomic transaction!
        """
        new_order = list(speaker_list.safe_speakers_qs().values_list("pk", flat=True))
        result = speaker_list.speaker_items.filter(
            order__isnull=False, safe_pos=True
        ).aggregate(Max("order"))
        max_order = result["order__max"]
        if max_order is None:
            start_order = 1
        else:
            start_order = max_order + 1
        for order, speaker in enumerate(
            speaker_list.speakers_unsafe_created_qs().all(), start_order
        ):
            speaker.order = order
            speaker.save()
            new_order.append(speaker.pk)
        return new_order
