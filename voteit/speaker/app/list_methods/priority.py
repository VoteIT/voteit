from collections import Counter
from typing import List

from pydantic import validator
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

    @validator("max_times", pre=True)
    def set_to_zero_when_falsy(cls, v):
        """
        This is kind of a bugfix for frontend, but no harm
        >>> PrioritySettingsSchema(max_times="")
        PrioritySettingsSchema(max_times=0)

        >>> PrioritySettingsSchema(max_times=None)
        PrioritySettingsSchema(max_times=0)
        """
        if not v:
            return 0
        return v


@list_method
class Priority(ListMethod):
    name = "priority"
    title = "Prioritise users who haven't spoken"
    description = (
        "Users who've spoken less than others in the queue will be prioritised."
    )
    settings_schema = PrioritySettingsSchema

    def reorder(self, speaker_list: SpeakerList) -> List[int]:
        """
        Prioritise according to spoken times. Just return the items, don't touch any data
        """
        initial_queue = speaker_list.get_user_pk_in_queue_created_order()
        # Fetch order and respect cached setting, but don't assume the values there are correct!
        sort_vals = [x for x in speaker_list.order_list if x in initial_queue]
        sort_vals.extend(x for x in initial_queue if x not in sort_vals)
        spoken_count = Counter()
        for v in speaker_list.speaker_items.filter(seconds__isnull=False).values_list(
            "user_id", flat=True
        ):
            spoken_count[v] += 1
        if speaker_list.speaker_system.safe_positions:
            safe_speakers = sort_vals[: speaker_list.speaker_system.safe_positions]
            speakers_to_sort = sort_vals[speaker_list.speaker_system.safe_positions :]
        else:
            safe_speakers = []
            speakers_to_sort = sort_vals
        new_order = []
        # A lower value is better, essentially "how many times have this person spoklen before?
        user_cmp_vals = {}
        max_times = self.speaker_system.settings.max_times
        for user_pk in speakers_to_sort:
            # user_cmp_vals[user_pk] = self.get_cmp_val(speaker_list, user_pk)
            count = spoken_count.get(user_pk, 0)
            if max_times:
                user_cmp_vals[user_pk] = min(count, max_times)
            else:
                user_cmp_vals[user_pk] = count
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
