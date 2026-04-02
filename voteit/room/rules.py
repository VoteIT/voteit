from __future__ import annotations
import rules
from typing import TYPE_CHECKING

from rules import always_allow

from voteit.core import PERM
from voteit.core.decorators import predicate
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_not_archived
from voteit.room import ROOM_PERM_HANDLE_SPEAKER
from voteit.room.models import Room
from voteit.speaker.rules import is_speaker_moderator

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


@predicate
def is_handler(user: AbstractUser, context: Room) -> bool:
    return context.handler is not None and user == context.handler


rules.add_perm(Room.get_perm(PERM.ADD), meeting_not_archived & is_moderator)
rules.add_perm(Room.get_perm(PERM.VIEW), always_allow)  # Handled by queryset
rules.add_perm(Room.get_perm(PERM.CHANGE), meeting_not_archived & is_moderator)
rules.add_perm(Room.get_perm(PERM.HANDLE), is_handler)
rules.add_perm(
    Room.get_perm(ROOM_PERM_HANDLE_SPEAKER),
    meeting_not_archived & (is_moderator | is_speaker_moderator),
)
rules.add_perm(Room.get_perm(PERM.DELETE), meeting_not_archived & is_moderator)
