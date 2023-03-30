from __future__ import annotations
from collections import Counter
from logging import getLogger
from typing import TYPE_CHECKING

from django.db.models import Sum
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from voteit.core.signals import roles_removed
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.exceptions import ElectoralRegisterError
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting

__all__ = ("GroupVotesBeforePoll",)
logger = getLogger(__name__)


@er_policy
class GroupVotesBeforePoll(ElectoralRegisterPolicy):
    """
    Create an electoral register when a poll enters upcoming or ongoing state,
    if it's needed. Set the latest created register for that poll and any other upcoming.

    GroupMembership objects must contain votes for this to work
    """

    name = "gv_auto_before_p"
    title = _("Weighted votes from group settings")
    description = _(
        "Groups have a total vote count which can be distributed among members "
        "that have the potential voter role. "
        "New electoral registers will be created whenever a poll starts if needed."
    )
    logger = logger
    handles_vote_weight = True
    available = False
    allow_trigger = True
    group_votes_active = True

    def get_voters(self, **kwargs) -> dict[int, int]:
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
        if group_total is None:
            group_total = 0
        if member_total > group_total:
            raise ElectoralRegisterError(
                f"get_voters returned more vote weight ({member_total}) "
                f"than the groups total vote weight ({group_total})"
            )
        return dict(counter)

    def pre_apply(self, poll: Poll, target: str):
        self.create_er()  # Won't trigger unless needed


@receiver(roles_removed, sender=MeetingRoles)
def clear_gm_votes_when(instance: MeetingRoles, roles=(), **kw):
    if ROLE_POTENTIAL_VOTER in roles:
        meeting: Meeting = instance.context
        if meeting.er_policy_name == GroupVotesBeforePoll.name:
            for gm in GroupMembership.objects.filter(
                votes__gt=0, user=instance.user, meeting_group__meeting=meeting
            ):
                gm.votes = None
                gm.save()
