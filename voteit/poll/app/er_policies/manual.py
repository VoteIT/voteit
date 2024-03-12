from logging import getLogger

from django.utils.translation import gettext_lazy as _

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.registries import er_policy

__all__ = ("Manual",)
logger = getLogger(__name__)


@er_policy
class Manual(ElectoralRegisterPolicy):
    """
    Create manually
    """

    name = "manual"
    title = _("Fully manual")
    description = _(
        "No electoral registers will be created at all, you have to do it yourself! "
        "You need to hand-pick voters from any participants with the role potential voter."
    )
    logger = logger
    allow_manual = True
    require_manual = True
    handles_vote_weight = True

    def get_voters(self, *, weight_dict: dict[int, int], **kwargs) -> dict[int, int]:
        """
        :param weight_dict: user_pk as key and weight as value. Require user to be potential voter.
            Anything not in weight_dict will be skipped.
        """
        return {
            x: weight_dict[x]
            for x in self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
            if x in weight_dict
        }
