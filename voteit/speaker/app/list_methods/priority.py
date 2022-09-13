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

    def get_cmp_val(self, speaker_list: SpeakerList, user: int) -> int:
        count = self.get_spoken_count(speaker_list, user)
        max_times = (
            self.speaker_system.settings.max_times
        )  # max_times is the number of extra lists
        if max_times == 0:  # 0 = eternity
            return count
        return min(count, max_times + 1)

    def reorder(self, speaker_list: SpeakerList) -> List[int]:
        """
        Prioritise according to spoken times. Just return the items, don't touch any data
        """
        initial_queue = speaker_list.get_user_pk_in_queue_created_order()
        if speaker_list.speaker_system.safe_positions:
            safe_speakers = initial_queue[: speaker_list.speaker_system.safe_positions]
            speakers_to_sort = initial_queue[
                speaker_list.speaker_system.safe_positions :
            ]
        else:
            safe_speakers = []
            speakers_to_sort = initial_queue
        new_order = []
        # A lower value is better, essentially "how many times have this person spoklen before?
        user_cmp_vals = {}
        for user_pk in speakers_to_sort:
            user_cmp_vals[user_pk] = self.get_cmp_val(speaker_list, user_pk)
        for user_pk in speakers_to_sort:
            cmp_val = user_cmp_vals[user_pk]
            insert_at = len(new_order)
            for pk in reversed(new_order):
                if cmp_val >= user_cmp_vals[pk]:
                    break
                insert_at -= 1
            new_order.insert(insert_at, user_pk)
        new_order = safe_speakers + new_order
        return new_order
