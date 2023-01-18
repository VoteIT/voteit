import rules

from voteit.active.permissions import ActiveUserPermissions
from voteit.active.utils import active_enabled_for_meeting
from voteit.core.abcs import MeetingContext
from voteit.core.decorators import predicate
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_participant
from voteit.meeting.rules import meeting_upcoming_ongoing


@predicate
def users_active_component_enabled(user, context: MeetingContext):
    return isinstance(context, MeetingContext) and active_enabled_for_meeting(
        context.meeting
    )


rules.add_perm(
    ActiveUserPermissions.CHANGE,
    meeting_upcoming_ongoing
    & users_active_component_enabled
    & (is_moderator | is_participant),
)
rules.add_perm(ActiveUserPermissions.VIEW, is_moderator | is_participant)
