import rules

from voteit.active.models import ActiveUser
from voteit.active.utils import active_enabled_for_meeting
from voteit.core import PERM
from voteit.core.abcs import MeetingContext
from voteit.core.decorators import predicate
from voteit.meeting.rules import is_participant
from voteit.meeting.rules import meeting_upcoming_ongoing


@predicate
def users_active_component_enabled(user, context: MeetingContext):
    return isinstance(context, MeetingContext) and active_enabled_for_meeting(
        context.meeting
    )


rules.add_perm(
    ActiveUser.get_perm(PERM.CHANGE),
    meeting_upcoming_ongoing & users_active_component_enabled & is_participant,
)
rules.add_perm(ActiveUser.get_perm(PERM.VIEW), is_participant)
