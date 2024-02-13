from __future__ import annotations
import rules
from typing import TYPE_CHECKING

from voteit.core.decorators import predicate
from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived

from voteit.room.models import Room
from voteit.room.permissions import RoomPermissions

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


@predicate
def is_handler(user: AbstractUser, context: Room) -> bool:
    return context.handler is not None and user == context.handler


rules.add_perm(RoomPermissions.ADD, meeting_not_archived & is_moderator)
rules.add_perm(RoomPermissions.VIEW, can_view_meeting)
rules.add_perm(RoomPermissions.CHANGE, meeting_not_archived & is_moderator)
rules.add_perm(RoomPermissions.HANDLE, is_handler)
rules.add_perm(RoomPermissions.DELETE, meeting_not_archived & is_moderator)
