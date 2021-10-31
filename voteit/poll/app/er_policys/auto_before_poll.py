from logging import getLogger

from django.dispatch import receiver
from django.utils.translation import gettext as _
from django_fsm import pre_transition

from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy
from voteit.poll.workflows import PollWf


__all__ = ("AutoBeforePoll",)
logger = getLogger(__name__)


@er_policy
class AutoBeforePoll(ElectoralRegisterPolicy):
    """Create an electoral register when a poll enters upcoming or ongoing state,
    if it's needed. Set the latest created register for that poll and any other upcoming.

    Polls must have a meeting relation for this to work, since the electoral register
    is created from Meeting.potential_voters
    """

    name = "auto_before_poll"
    title = _("Automatic before poll")
    logger = logger

    def apply(self, poll: Poll):
        meeting = poll.meeting
        if meeting is None:  # pragma: no coverage
            # FIXME: We don't support this yet
            raise Exception("No meeting")
        meetings_er = meeting.new_electoral_register()
        if poll.electoral_register is None:
            self.logger.debug(
                "%s has no electoral register. Attaching %s", poll, meetings_er
            )
            poll.electoral_register = meetings_er
        elif poll.electoral_register != meetings_er:
            self.logger.debug(
                "%s has an outdated electoral register, changing to %s instead",
                poll,
                meetings_er,
            )
            poll.electoral_register = meetings_er
        else:
            self.logger.debug("%s already has the correct electoral register", poll)
            return
        # FIXME: This should probably be wrapped in a transaction
        poll.save()


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
        if meeting.er_policy_name == AutoBeforePoll.name:
            meeting.er_policy.apply(instance)
