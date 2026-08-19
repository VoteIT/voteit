from __future__ import annotations


from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class SpeakerListAdded(BaseObjectAdded):
    name = "speaker_list.added"


@outgoing
class SpeakerListChanged(BaseObjectChanged):
    name = "speaker_list.changed"


@outgoing
class SpeakerListDeleted(BaseObjectDeleted):
    name = "speaker_list.deleted"


@outgoing
class SpeakerSystemAdded(BaseObjectAdded):
    name = "speaker_system.added"


@outgoing
class SpeakerSystemChanged(BaseObjectChanged):
    name = "speaker_system.changed"


@outgoing
class SpeakerSystemDeleted(BaseObjectDeleted):
    name = "speaker_system.deleted"


@outgoing
class SpeakerChanged(BaseObjectChanged):
    name = "speaker.changed"


@outgoing
class SpeakerAdded(BaseObjectAdded):
    name = "speaker.added"


@outgoing
class SpeakerDeleted(BaseObjectDeleted):
    name = "speaker.deleted"
