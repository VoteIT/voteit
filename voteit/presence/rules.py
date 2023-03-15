import rules
from django.contrib.auth.models import AbstractUser

from voteit.core.abcs import MeetingContext
from voteit.core.decorators import predicate
from voteit.core.workflows import EnabledWf
from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_participant
from voteit.meeting.rules import meeting_upcoming_ongoing
from voteit.presence.components import PresenceCheckComponent
from voteit.presence.models import Presence
from voteit.presence.models import PresenceCheck
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.permissions import PresencePermissions
from voteit.presence.workflows import PresenceCheckWf


@predicate
def is_check_open(user: AbstractUser, instance: PresenceCheck):
    if isinstance(instance, PresenceCheck):
        return instance.state == PresenceCheckWf.OPEN
    return False


@predicate
def presence_component_active(user: AbstractUser, instance: MeetingContext):
    if instance.meeting:
        return instance.meeting.components.filter(
            component_name=PresenceCheckComponent.name, state=EnabledWf.ON
        ).exists()
    return False


rules.add_perm(
    PresenceCheckPermissions.ADD,
    meeting_upcoming_ongoing & is_moderator & presence_component_active,
)
rules.add_perm(
    PresenceCheckPermissions.CHANGE,
    is_check_open & is_moderator & presence_component_active,
)
rules.add_perm(PresenceCheckPermissions.DELETE, meeting_upcoming_ongoing & is_moderator)
rules.add_perm(PresenceCheckPermissions.VIEW, can_view_meeting)


@predicate
def is_present_user(user: AbstractUser, presence: Presence) -> bool:
    return isinstance(presence, Presence) and user is not None and user == presence.user


rules.add_perm(
    PresencePermissions.CHANGE,
    is_check_open & presence_component_active & (is_participant | is_moderator),
)
# GDPR might change this behaviour
rules.add_perm(PresencePermissions.VIEW, is_moderator | is_present_user)
