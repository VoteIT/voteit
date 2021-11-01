from __future__ import annotations
from logging import getLogger
from typing import TYPE_CHECKING

from django.dispatch import receiver
from django.utils.translation import gettext as _
from django_fsm import post_transition
from django_fsm import pre_transition
from typing import Set

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy
from voteit.poll.workflows import PollWf
from voteit.meeting.models import Meeting
from voteit.presence.models import PresenceCheck
from voteit.presence.workflows import PresenceCheckWf

if TYPE_CHECKING:
    from voteit.poll.models import ElectoralRegister

__all__ = ("PresenceCheckPolicy",)

logger = getLogger(__name__)


@er_policy
class PresenceCheckPolicy(ElectoralRegisterPolicy):
    """
    Any completed presence check causes a new electoral register
    """

    name = "presence_check"
    title = _("Closing a presence check will set a new electoral register.")
    logger = logger

    def get_voters(self, presence_check=None, **kwargs) -> Set[int]:
        if presence_check is None:
            # FIXME: What kind of exception here?
            raise Exception("No presence check exists")
        potential_voters = self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        if potential_voters is None:
            # FIXME: What kind of exception here?
            raise Exception("Not a single elegible voter")
        present_potential_voters = presence_check.present_users.filter(
            pk__in=potential_voters
        )
        return set(present_potential_voters.values_list("pk", flat=True))


@receiver(post_transition, sender=PresenceCheck)
def create_new_er_from_present_users(
    instance: PresenceCheck, source: str, target: str, **kwargs
):
    if target == PresenceCheckWf.CLOSED:
        if instance.meeting.er_policy_name == PresenceCheckPolicy.name:
            instance.meeting.er_policy.create_er(presence_check=instance)
