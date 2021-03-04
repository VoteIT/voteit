from django.contrib.auth.models import AbstractUser
from django.db import models
from typing import List

from pydantic.main import BaseModel
from voteit.speaker.abcs import ListMethod
from voteit.speaker.models import SpeakerList
from voteit.speaker.registries import list_method


class PrioritySettingsSchema(BaseModel):
    max_times: int = 0
    # "Number of times to prioritise a speaker. "
    # "0 means always prioritise speakers who've spoken less than someone else."

    class Config:
        allow_mutation = False


@list_method
class Priority(ListMethod):
    name = "priority"
    title = "Prioritise users who haven't spoken"
    description = (
        "Users who've spoken less than others in the queue will be prioritised."
    )
    settings_schema = PrioritySettingsSchema

    def get_spoken_count(self, speaker_list: SpeakerList, user: AbstractUser) -> int:
        return speaker_list.speaker_items.filter(order__isnull=True, user=user).count()

    def get_cmp_val(self, speaker_list: SpeakerList, user: AbstractUser) -> int:
        count = self.get_spoken_count(speaker_list, user)
        max_times = self.speaker_system.settings.max_times
        if max_times and count > max_times:
            return max_times
        return count

    def reorder(self, speaker_list: SpeakerList) -> List[int]:
        """ Prioritise according to spoken times """
        result = speaker_list.speaker_items.filter(
            order__isnull=False, safe_pos=True
        ).aggregate(models.Max("order"))
        max_order = result["order__max"]
        if max_order is None:
            start_order = 1
        else:
            start_order = max_order + 1
        # Retrieve the speakers in chronological order and insert them in a new list
        new_order = []
        speakers = {}
        speakers_to_sort = tuple(speaker_list.speakers_unsafe_created_qs().all())
        # A lower value is better, essentially "how many times have this person spoklen before?
        speaker_cmp_vals = {}
        for speaker in speakers_to_sort:
            speakers[speaker.pk] = speaker
            speaker_cmp_vals[speaker.pk] = self.get_cmp_val(speaker_list, speaker.user)
        for speaker in speakers_to_sort:
            cmp_val = speaker_cmp_vals[speaker.pk]
            insert_at = len(new_order)
            for pk in reversed(new_order):
                if cmp_val >= speaker_cmp_vals[pk]:
                    break
                insert_at -= 1
            new_order.insert(insert_at, speaker.pk)
        for pk in new_order:
            speaker = speakers[pk]
            speaker.order = new_order.index(pk) + start_order
            speaker.save()
        # Insert the safe speakers before
        return [x.pk for x in speaker_list.safe_speakers_qs().all()] + new_order
