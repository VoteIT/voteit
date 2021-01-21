from __future__ import annotations

from abc import abstractmethod, ABC
from logging import getLogger
from typing import TYPE_CHECKING, List, Optional

from django.db.models import Max
from pydantic.main import BaseModel


if TYPE_CHECKING:
    from voteit.speaker.models import SpeakerListSystem
    from voteit.speaker.models import SpeakerList

logger = getLogger(__name__)


class ListMethod(ABC):
    def __init__(self, list_system: SpeakerListSystem):
        self.list_system = list_system

    @property
    @abstractmethod
    def name(self) -> str:
        """ Unique name for method """

    @property
    @abstractmethod
    def title(self) -> str:
        """ Human-readable title """

    @property
    @abstractmethod
    def description(self) -> str:
        """ Human-readable explanation of what this does. """

    @property
    def settings_schema(self) -> Optional[BaseModel]:
        """ Possible settings schema for this speaker list method.
            Will be enforced if it exists
        """
        return None

    def reorder(self, speaker_list: SpeakerList) -> List[int]:
        """ Override this method to implement actual quotas or similar.
            The default one simply orders users according to the order they entered the list.

            This method returns the primary keys of the speakers according to the new order.
            Make sure to include the safe speakers!
        """
        new_order = [x.pk for x in speaker_list.safe_speakers_qs().all()]
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
