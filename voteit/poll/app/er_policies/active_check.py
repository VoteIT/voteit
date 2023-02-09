from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import GroupVoteElectoralRegisterPolicy
from voteit.poll.registries import er_policy

if TYPE_CHECKING:
    from voteit.poll.models import Poll

__all__ = ("ActiveCheckPolicy",)

logger = getLogger(__name__)

User = get_user_model()


@er_policy
class ActiveCheckPolicy(GroupVoteElectoralRegisterPolicy):
    """
    Any completed presence check causes a new electoral register
    """

    name = "active_check"
    title = _("Active check")
    description = _(
        "All users who're registered as active and have the potential voter role will be added when a poll starts. "
        "If group voting is used, the votes will be equally distributed among the active members of that group."
    )
    logger = logger
    allow_manual = True
    handles_vote_weight = False
    handles_personal_vote = True

    def get_voters(self, **kwargs) -> dict[int, int]:
        potential_voters = self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        if potential_voters is None:  # pragma: no cover
            # FIXME: What kind of exception should we use here?
            raise Exception("Not a single eligible voter")
        users_qs = User.objects.filter(pk__in=potential_voters).filter(
            pk__in=self.meeting.active_users.values_list("user_id", flat=True)
        )
        if self.meeting.group_votes_active:
            return self.meeting.er_policy.calc_group_votes_equal(only_users_qs=users_qs)
        else:
            return {x: 1 for x in users_qs.values_list("pk", flat=True)}

    def pre_apply(self, poll: Poll, target: str):
        self.create_er()  # Won't trigger unless needed

    def poll_will_have_voters(self, **kwargs) -> bool:
        return bool(self.get_voters(**kwargs))
