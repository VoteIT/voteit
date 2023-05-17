from __future__ import annotations
from typing import TYPE_CHECKING

from voteit.speaker.abcs import ListMethod
from voteit.speaker.registries import list_method

if TYPE_CHECKING:
    from voteit.speaker.models import SpeakerList


@list_method
class Simple(ListMethod):
    name = "simple"
    title = "Simple flat list that maintains order chronologically"
    description = "It's just a queue with no settings. It won't prioritise speakers."

    def reorder(self, speaker_list: SpeakerList) -> list[int]:
        return speaker_list.get_user_pk_in_queue_created_order()
