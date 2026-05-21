import rules

from voteit.core import PERM
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_upcoming_ongoing
from voteit.token_api.models import MeetingAPIKey

# These permissions are for the keys themselves. Who can create keys etc
rules.add_perm(MeetingAPIKey.get_perm(PERM.VIEW), is_moderator)
rules.add_perm(
    MeetingAPIKey.get_perm(PERM.ADD), is_moderator & meeting_upcoming_ongoing
)
rules.add_perm(
    MeetingAPIKey.get_perm(PERM.CHANGE), is_moderator & meeting_upcoming_ongoing
)
rules.add_perm(
    MeetingAPIKey.get_perm(PERM.DELETE), is_moderator
)  # This is really revoke
