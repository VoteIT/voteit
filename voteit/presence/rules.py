import rules
from django.contrib.auth.models import AbstractUser
from rules import always_deny

from voteit.core import PERM
from voteit.core.abcs import MeetingContext
from voteit.core.decorators import predicate
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import is_participant
from voteit.presence.components import PresenceCheckComponent
from voteit.presence.models import PresenceCheck
from voteit.presence.workflows import PresenceCheckWf


@predicate
def is_check_open(user: AbstractUser, instance: PresenceCheck):
    if isinstance(instance, PresenceCheck):
        return instance.state == PresenceCheckWf.OPEN
    return False


@predicate
def presence_component_active(user: AbstractUser, instance: MeetingContext):
    if instance.meeting:
        return instance.meeting.component_enabled(PresenceCheckComponent.name)
    return False


rules.add_perm(PresenceCheck.get_perm(PERM.ADD), always_deny)
rules.add_perm(
    PresenceCheck.get_perm(PERM.CHANGE),
    is_check_open & is_moderator & presence_component_active,
)
rules.add_perm(PresenceCheck.get_perm(PERM.DELETE), is_moderator)
rules.add_perm(PresenceCheck.get_perm(PERM.VIEW), is_participant)
