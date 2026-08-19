from __future__ import annotations

from typing import Literal


from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class SpeakerListChanged(ObjectAddedOrChanged):
    action: Literal["speaker_list.changed"] = "speaker_list.changed"


@outgoing
class SpeakerListDeleted(ObjectDeleted):
    action: Literal["speaker_list.deleted"] = "speaker_list.deleted"


@outgoing
class SpeakerSystemChanged(ObjectAddedOrChanged):
    action: Literal["speaker_system.changed"] = "speaker_system.changed"


@outgoing
class SpeakerSystemDeleted(ObjectDeleted):
    action: Literal["speaker_system.deleted"] = "speaker_system.deleted"


@outgoing
class SpeakerChanged(ObjectAddedOrChanged):
    action: Literal["speaker.changed"] = "speaker.changed"


@outgoing
class SpeakerDeleted(ObjectDeleted):
    action: Literal["speaker.deleted"] = "speaker.deleted"
