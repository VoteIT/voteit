from django.dispatch import receiver
from django.utils.translation import gettext as _
from django_fsm import pre_transition

from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy
from voteit.poll.workflows import PollWf


@er_policy
class AutoBeforePoll(ElectoralRegisterPolicy):
    """ Create an electoral register when a poll enters upcoming or ongoing state,
        if it's needed. Set the latest created register for that poll and any other upcoming.

        Polls must have a meeting relation for this to work, since the electoral register
        is created from Meeting.potential_voters
    """

    title = _("Automatic before poll")

    def apply(self, poll: Poll):
        meeting = poll.meeting
        if meeting is None:
            # FIXME:
            raise Exception("No meeting")
        # FIXME: gör röstlängd här


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
        policy = meeting.get_policy(AutoBeforePoll)
        if policy is not None:
            policy.apply(instance)
