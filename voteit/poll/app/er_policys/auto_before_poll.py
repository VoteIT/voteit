from logging import getLogger

from django.dispatch import receiver
from django.utils.translation import gettext as _
from django_fsm import pre_transition

from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.models import Poll
from voteit.poll.models import ElectoralRegister
from voteit.poll.registries import er_policy
from voteit.poll.workflows import PollWf
from voteit.meeting.models import Meeting


logger = getLogger(__name__)


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
        meetings_er = poll.meeting.get_latest_er()
        if meetings_er is None:
            logger.debug("%s has no electoral register, creating...", meeting)
            meetings_er = self.create_er(meeting)
        elif set(meetings_er.voters.all()) != set(meeting.potential_voters.all()):
            # FIXME: Is there a smarter way to make this comparison?
            logger.debug(
                "%s electoral register is outdated. Creating a new one.", meeting
            )
            meetings_er = self.create_er(meeting)
        if poll.electoral_register is None:
            logger.debug(
                "%s has no electoral register. Attaching %s", poll, meetings_er
            )
            poll.electoral_register = meetings_er
        elif poll.electoral_register != meetings_er:
            logger.debug(
                "%s has an outdated electoral register, changing to %s instead",
                poll,
                meetings_er,
            )
            poll.electoral_register = meetings_er
        else:
            logger.debug("%s already has the correct electoral register", poll)

    def create_er(self, meeting: Meeting) -> ElectoralRegister:
        er = ElectoralRegister.objects.create(meeting=meeting)
        er.voters.set(meeting.potential_voters.all())
        return er


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
        if isinstance(meeting.er_policy, AutoBeforePoll):
            meeting.er_policy.apply(instance)
