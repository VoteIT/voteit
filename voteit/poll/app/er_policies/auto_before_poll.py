from logging import getLogger

from django.utils.translation import gettext_lazy as _

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import GroupVoteElectoralRegisterPolicy
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy

__all__ = ("AutoBeforePoll",)
logger = getLogger(__name__)


@er_policy
class AutoBeforePoll(GroupVoteElectoralRegisterPolicy):
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
    handles_personal_vote = True

    def get_voters(self, **kwargs) -> dict[int, int]:
        if self.meeting.group_votes_active:
            return self.calc_group_votes_equal()
        else:
            return {
                x: 1 for x in self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
            }

    def pre_apply(self, poll: Poll, target: str):
        self.create_er()  # Won't trigger unless needed
