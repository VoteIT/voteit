from logging import getLogger

from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from voteit.active.utils import active_enabled_for_meeting
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.app.er_policies.utils import calc_group_votes_equal
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy

__all__ = ("GroupAutoRandomBeforePoll",)
logger = getLogger(__name__)
User = get_user_model()


@er_policy
class GroupAutoRandomBeforePoll(ElectoralRegisterPolicy):
    """
    Create an electoral register when a poll enters upcoming or ongoing state,
    if it's needed. Set the latest created register for that poll and any other upcoming.

    Polls must have a meeting relation for this to work, since the electoral register
    is created from Meeting.potential_voters
    """

    name = "group_auto_eq_rnd_bf"
    title = _("Equal weighted group votes")
    description = _(
        "Any group members share votes within the group equally. If they can't be distributed evenly, "
        "the rest will be randomized. Only potential voters may receive a vote."
    )
    logger = logger
    handles_vote_weight = True
    group_votes_active = True
    allow_trigger = True
    handles_active_check = True
    handles_delegate_to = True

    def get_voters(self, **kwargs) -> dict[int, int]:
        if active_enabled_for_meeting(self.meeting):
            return calc_group_votes_equal(
                meeting=self.meeting,
                only_users_qs=User.objects.filter(
                    pk__in=self.meeting.active_users.values_list("user_id", flat=True)
                ),
            )
        return calc_group_votes_equal(meeting=self.meeting)

    def pre_apply(self, poll: Poll):
        self.create_er()  # Won't trigger unless needed
