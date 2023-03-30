from logging import getLogger

from django.utils.translation import gettext_lazy as _

from voteit.active.utils import active_enabled_for_meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy

__all__ = ("AutoBeforePoll",)
logger = getLogger(__name__)


@er_policy
class AutoBeforePoll(ElectoralRegisterPolicy):
    """
    Create an electoral register when a poll enters upcoming or ongoing state,
    if it's needed. Set the latest created register for that poll and any other upcoming.

    Polls must have a meeting relation for this to work, since the electoral register
    is created from Meeting.potential_voters
    """

    name = "auto_before_poll"
    title = _("Automatic before poll")
    description = _(
        "Any users with potential voter status will be added to the electoral register when a poll starts."
    )
    logger = logger
    handles_vote_weight = False
    allow_trigger = True
    handles_active_check = True
    group_votes_active = False

    def get_voters(self, **kwargs) -> dict[int, int]:
        voters = self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        if active_enabled_for_meeting(self.meeting):
            voters = self.meeting.active_users.filter(user_id__in=voters).values_list(
                "user_id", flat=True
            )
        return {x: 1 for x in voters}

    def pre_apply(self, poll: Poll, target: str):
        self.create_er()  # Won't trigger unless needed
