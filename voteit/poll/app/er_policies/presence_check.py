from __future__ import annotations

from logging import getLogger

from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django_fsm import post_transition

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.app.er_policies.utils import calc_group_votes_equal
from voteit.poll.exceptions import ElectoralRegisterError
from voteit.poll.registries import er_policy
from voteit.presence.models import PresenceCheck
from voteit.presence.workflows import PresenceCheckWf

__all__ = ("PresenceCheckPolicy",)

logger = getLogger(__name__)


@er_policy
class PresenceCheckPolicy(ElectoralRegisterPolicy):
    """
    Any completed presence check causes a new electoral register
    """

    name = "presence_check"
    title = _("Presence check")
    description = _(
        "Any user who's both present and has the potential voter role will be added to the electoral "
        "register when it closes. "
        "If group votes is activated, the votes will be distributed equally between present members."
    )
    logger = logger
    allow_manual = True
    handles_vote_weight = True

    def get_voters(self, presence_check=None, **kwargs) -> dict[int, int]:
        if presence_check is None:  # pragma: no coverage
            raise ElectoralRegisterError("No presence check exists")
        potential_voters = self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        if not potential_voters.exists():
            raise ElectoralRegisterError("Not a single eligible voter")
        present_potential_voters = presence_check.present_users.filter(
            pk__in=potential_voters
        )
        if self.meeting.group_votes_active:
            return calc_group_votes_equal(
                meeting=self.meeting, only_users_qs=present_potential_voters
            )
        else:
            return {x: 1 for x in present_potential_voters.values_list("pk", flat=True)}


@receiver(post_transition, sender=PresenceCheck)
def create_new_er_from_present_users(
    instance: PresenceCheck, source: str, target: str, **kwargs
):
    if target == PresenceCheckWf.CLOSED:
        if instance.meeting.er_policy_name == PresenceCheckPolicy.name:
            instance.meeting.er_policy.create_er(presence_check=instance)
