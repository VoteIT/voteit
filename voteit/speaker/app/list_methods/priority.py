from pydantic import validator
from pydantic.main import BaseModel

from voteit.speaker.abcs import ListMethod
from voteit.speaker.models import Speaker
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

    def reorder(self, previous_speakers, incoming_order):
        """
        Prioritise according to spoken times. Just return the items, don't touch any data
        """
        max_priority = self.speaker_system.settings.max_times or 1_000_000

        def order_key(speaker: Speaker) -> tuple[int, int]:
            return (
                min(speaker.spoken_count, max_priority),
                incoming_order.index(speaker),
            )

        yield from sorted(incoming_order, key=order_key)
