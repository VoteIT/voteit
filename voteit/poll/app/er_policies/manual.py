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
    title = _("Manual only")
    logger = logger
    handles_vote_weight = True

    def get_voters(self, *, weight_dict: dict[int, int], **kwargs) -> dict[int, int]:
        """
        :param weight_dict: user_pk as key and weight as value, or simply skip it for 1
        """
        return dict(
            (x, weight_dict.get(x, 1))
            for x in self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        )
