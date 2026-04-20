import rules

from voteit.core import PERM
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_participant
from voteit.meeting.rules import meeting_not_archived
from voteit.room import ROOM_PERM_HANDLE_SPEAKER
from voteit.room.models import Room
from voteit.speaker.rules import is_speaker_moderator


rules.add_perm(Room.get_perm(PERM.ADD), meeting_not_archived & is_moderator)
rules.add_perm(Room.get_perm(PERM.VIEW), is_participant)  # Messages use this
rules.add_perm(Room.get_perm(PERM.CHANGE), meeting_not_archived & is_moderator)
rules.add_perm(Room.get_perm(PERM.HANDLE), meeting_not_archived & is_moderator)
rules.add_perm(
    Room.get_perm(ROOM_PERM_HANDLE_SPEAKER),
    meeting_not_archived & (is_moderator | is_speaker_moderator),
)
rules.add_perm(Room.get_perm(PERM.DELETE), meeting_not_archived & is_moderator)
