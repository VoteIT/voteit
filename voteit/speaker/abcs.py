from __future__ import annotations

from abc import abstractmethod
from logging import getLogger
from typing import TYPE_CHECKING, Optional, List

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.db.models import Max

from voteit.core.models import ABCModel

if TYPE_CHECKING:
    from voteit.speaker.models import SpeakerListSystem
    from voteit.speaker.models import Speaker
    from voteit.speaker.models import SpeakerList

logger = getLogger(__name__)


class ListMethod(ABCModel):
    list_system_rel = GenericRelation(
        "speaker.SpeakerListSystem", object_id_field="method_id", content_type_field="method_type"
    )

    class Meta:
        abstract = True

    @property
    def list_system(self) -> SpeakerListSystem:
        return self.list_system_rel.get()

    @property
    @abstractmethod
    def title(self) -> str:
        """ Human-readable title """

    @property
    @abstractmethod
    def description(self) -> str:
        """ Human-readable explanation of what this does. """

    def reorder(self, speaker_list: SpeakerList) -> List[int]:
        """ Override this method to implement actual quotas or similar.
            The default one simply orders users according to the order they entered the list.

            This method returns the primary keys of the speakers according to the new order.
            Make sure to include the safe speakers!
        """
        new_order = [x.pk for x in speaker_list.safe_speakers_qs().all()]
        result = speaker_list.speaker_items.filter(order__isnull=False, safe_pos=True).aggregate(Max("order"))
        max_order = result["order__max"]
        if max_order is None:
            start_order = 1
        else:
            start_order = max_order + 1
        for order, speaker in enumerate(speaker_list.speakers_unsafe_created_qs().all(), start_order):
            speaker.order = order
            speaker.save()
            new_order.append(speaker.pk)
        return new_order
