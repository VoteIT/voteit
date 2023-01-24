from collections import Counter
from logging import getLogger

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

from voteit.meeting.models import GroupMembership
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import GroupVoteElectoralRegisterPolicy
from voteit.poll.exceptions import ElectoralRegisterError
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy

__all__ = ("GroupVotesBeforePoll",)
logger = getLogger(__name__)


@er_policy
class GroupVotesBeforePoll(GroupVoteElectoralRegisterPolicy):
    """
    Create an electoral register when a poll enters upcoming or ongoing state,
    if it's needed. Set the latest created register for that poll and any other upcoming.

    GroupMembership objects must contain votes for this to work
    """

    name = "gv_auto_before_p"
    title = _("Group votes automatic before poll")
    logger = logger
    handles_vote_weight = True
    handles_personal_vote = False
    available = False

    def get_voters(self, **kwargs) -> dict[int, int]:
        if self.meeting.group_votes_active:
            groups_qs = self.meeting.groups.filter(votes__gt=0)
            potential_voters = self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
            counter = Counter()
            gm_qs = GroupMembership.objects.filter(
                user__in=potential_voters, meeting_group__in=groups_qs, votes__gt=0
            )
            for item in gm_qs.values("user", "votes"):
                counter[item["user"]] += item["votes"]
            member_total = counter.total()
            group_total = groups_qs.aggregate(Sum("votes"))["votes__sum"]
            if member_total > group_total:
                raise ElectoralRegisterError(
                    f"get_voters returned more vote weight ({member_total}) "
                    f"than the groups total vote weight ({group_total})"
                )
            return dict(counter)
        else:
            raise ElectoralRegisterError(
                "This should never be active for meetings without group votes"
            )

    def pre_apply(self, poll: Poll, target: str):
        self.create_er()  # Won't trigger unless needed
