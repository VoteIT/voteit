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
        safe_positions = self.speaker_system.safe_positions
        user_to_speaker_dict = {
            x.user_id: x
            for x in speaker_list.speakers_in_queue_or_speaking(
                spoken_count=True
            ).order_by("created")
        }
        # Fetch order and respect cached setting, but don't assume the values there are correct!
        sort_vals = [x for x in speaker_list.order_list if x in user_to_speaker_dict]
        sort_vals.extend(x for x in user_to_speaker_dict if x not in sort_vals)
        safe_speakers = []
        if safe_positions:
            for user_id in list(sort_vals):
                # In case we touch current speaker, include them but don't consume safe pos.
                if user_to_speaker_dict[user_id].started:
                    safe_positions += 1
                sort_vals.remove(user_id)
                safe_speakers.append(user_id)
                if len(safe_speakers) == safe_positions:
                    break
        # A lower value is better, essentially "how many times have this person spoken before?"
        max_times = self.speaker_system.settings.max_times
        if max_times:
            user_cmp_vals = {
                k: min(v.spoken_count, max_times)
                for k, v in user_to_speaker_dict.items()
            }
        else:
            user_cmp_vals = {k: v.spoken_count for k, v in user_to_speaker_dict.items()}
        new_order = []
        for user_pk in sort_vals:
            cmp_val = user_cmp_vals[user_pk]
            insert_at = len(new_order)
            for pk in reversed(new_order):
                if cmp_val >= user_cmp_vals[pk]:
                    break
                insert_at -= 1
            new_order.insert(insert_at, user_pk)
        return safe_speakers + new_order
