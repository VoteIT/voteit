from __future__ import annotations

from typing import Literal

from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class MeetingInviteChanged(ObjectAddedOrChanged):
    action: Literal["meeting_invite.changed"] = "meeting_invite.changed"


@outgoing
class MeetingInviteDeleted(ObjectDeleted):
    action: Literal["meeting_invite.deleted"] = "meeting_invite.deleted"
