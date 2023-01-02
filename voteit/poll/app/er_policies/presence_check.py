from __future__ import annotations

from logging import getLogger

from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django_fsm import post_transition

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import GroupVoteElectoralRegisterPolicy
from voteit.poll.registries import er_policy
from voteit.presence.models import PresenceCheck
from voteit.presence.workflows import PresenceCheckWf

__all__ = ("PresenceCheckPolicy",)

logger = getLogger(__name__)


@er_policy
class PresenceCheckPolicy(GroupVoteElectoralRegisterPolicy):
    """
    Any completed presence check causes a new electoral register
    """

    name = "presence_check"
    title = _("Closing a presence check will set a new electoral register.")
    logger = logger
    handles_vote_weight = False
    handles_personal_vote = True

    def get_voters(self, presence_check=None, **kwargs) -> dict[int, int]:
        if presence_check is None:
            # FIXME: What kind of exception here?
            raise Exception("No presence check exists")
        potential_voters = self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        if potential_voters is None:
            # FIXME: What kind of exception should we use here?
            raise Exception("Not a single eligible voter")
        present_potential_voters = presence_check.present_users.filter(
            pk__in=potential_voters
        )
        if self.meeting.group_votes_active:
            return self.meeting.er_policy.calc_group_votes_equal(
                only_users_qs=present_potential_voters
            )
        else:
            return {x: 1 for x in present_potential_voters.values_list("pk", flat=True)}

    def poll_will_have_voters(self, **kwargs):
        """
        Check for presence check can't be done this way, but it shouldn't block.
        This check is run when starting the poll so other checks will block start of the ER is empty.
        """
        return True


@receiver(post_transition, sender=PresenceCheck)
def create_new_er_from_present_users(
    instance: PresenceCheck, source: str, target: str, **kwargs
):
    if target == PresenceCheckWf.CLOSED:
        if instance.meeting.er_policy_name == PresenceCheckPolicy.name:
            instance.meeting.er_policy.create_er(presence_check=instance)
