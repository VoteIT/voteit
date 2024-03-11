from logging import getLogger

from django.utils.translation import gettext_lazy as _

from voteit.active.utils import active_enabled_for_meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy

__all__ = ("ManualTrigger",)
logger = getLogger(__name__)


@er_policy
class ManualTrigger(ElectoralRegisterPolicy):
    """
    Manually trigger creation of electoral registers.
    """

    name = "manual_trigger"
    title = _("Manual trigger")
    description = _(
        "Create electoral registers from potential voters. Simply click the button on electoral registers page."
    )
    logger = logger
    handles_vote_weight = False
    allow_trigger = True
    require_manual = True
    handles_active_check = True
    group_votes_active = False

    def get_voters(self, **kwargs) -> dict[int, int]:
        voters = self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        if active_enabled_for_meeting(self.meeting):
            voters = self.meeting.active_users.filter(user_id__in=voters).values_list(
                "user_id", flat=True
            )
        return {x: 1 for x in voters}
