from logging import getLogger

from django.utils.translation import gettext_lazy as _

from voteit.poll.abcs import GroupVoteElectoralRegisterPolicy
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy
from voteit.poll.exceptions import ElectoralRegisterError

__all__ = ("GroupAutoRandomBeforePoll",)
logger = getLogger(__name__)


@er_policy
class GroupAutoRandomBeforePoll(GroupVoteElectoralRegisterPolicy):
    """
    Create an electoral register when a poll enters upcoming or ongoing state,
    if it's needed. Set the latest created register for that poll and any other upcoming.

    Polls must have a meeting relation for this to work, since the electoral register
    is created from Meeting.potential_voters
    """

    name = "group_auto_eq_rnd_bf"
    title = _("Equal group votes")
    description = _(
        "Any group members share votes within the group equally. If they can't be distributed evenly, "
        "the rest will be randomized. Only potential voters may receive a vote."
    )
    logger = logger
    handles_vote_weight = False
    handles_personal_vote = True
    allow_trigger = True

    def get_voters(self, **kwargs) -> dict[int, int]:
        if self.meeting.group_votes_active:
            return self.calc_group_votes_equal()
        # pragma:no cover
        raise ElectoralRegisterError(
            "Group votes isn't active, invalid electoral register policy"
        )

    def pre_apply(self, poll: Poll, target: str):
        self.create_er()  # Won't trigger unless needed
