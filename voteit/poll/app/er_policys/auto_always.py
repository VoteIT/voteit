from logging import getLogger

from django.dispatch import receiver
from django.utils.translation import gettext as _
from django_fsm import pre_transition

from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policys import AutoBeforePoll
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy
from voteit.poll.workflows import PollWf
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles

__all__ = ("AutoAlways",)
logger = getLogger(__name__)


@er_policy
class AutoAlways(AutoBeforePoll):
    """As soon as the potential voter role changes, create a new electoral register and attach it
    even to ongoing polls. This is only meant for demo meetings"""

    name = "auto_always"
    title = _("Demo meeting: Always update electoral register")
    logger = logger


def _maybe_create_and_update(instance: MeetingRoles, roles=()):
    if ROLE_POTENTIAL_VOTER in roles:
        meeting: Meeting = instance.context
        if meeting.er_policy_name == AutoAlways.name:
            for poll in meeting.polls.filter(state=PollWf.ONGOING):
                # This will duplicate searches and checks over polls,
                # but since this is only a demo we don't need to optimize for speed
                meeting.er_policy.apply(poll)


@receiver(roles_added, sender=MeetingRoles)
def new_er_voter_added(instance: MeetingRoles, roles=(), **kw):
    _maybe_create_and_update(instance, roles=roles)


@receiver(roles_removed, sender=MeetingRoles)
def new_er_voter_removed(instance: MeetingRoles, roles=(), **kw):
    _maybe_create_and_update(instance, roles=roles)


@receiver(pre_transition, sender=Poll)
def handle_poll_state_change(
    sender: Poll, instance: Poll, source: str, target: str, **kwargs
):
    if target in (PollWf.UPCOMING, PollWf.ONGOING):
        # A state we want to handle
        meeting = instance.meeting
        if meeting is None:
            # This method isn't runnable if poll isn't attached to a meeting
            # Normally this would never happen, but during tests it will...
            return
        if meeting.er_policy_name == AutoAlways.name:
            meeting.er_policy.apply(instance)
