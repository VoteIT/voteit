from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from voteit.active.utils import active_enabled_for_meeting
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.exceptions import ElectoralRegisterError
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy

if TYPE_CHECKING:
    from django.db.models import QuerySet

DELEGAT_FULLMAKT = "del_2"
DELEGAT = "del_1"
SUPPLEANT = "suppleant"

logger = getLogger(__name__)


@er_policy
class SKKFum(ElectoralRegisterPolicy):
    """
    Handle SKK Fullmäktige
    """

    name = "skk_kfum"
    title = "SKK Kennelfullmäktige"
    description = (
        "Fördelar röster baserat på roll i grupper. Rollerna är "
        "Delegat med fullmakt, delegat och suppleant. Ingen kan ha mer än 2 röster. "
        "Delegat-rollerna får 2 röster innan suppleant får 1."
    )
    logger = logger
    handles_vote_weight = False
    available = False  # Not installed manually
    allow_trigger = True
    handles_active_check = True

    def iterate_and_pick_voters(
        self,
        vote_power: dict[int, int],
        gm_qs: QuerySet[GroupMembership],
        pickset: set[int],
    ):
        """
        Adjust vote power in place
        """
        for gm in gm_qs:
            if gm.user_id in pickset:
                continue
            # pick vote
            if vote_power[gm.meeting_group_id]:
                vote_power[gm.meeting_group_id] -= 1
                pickset.add(gm.user_id)

    def get_voters(self, **kwargs) -> dict[int, int]:
        relevant_roles = list(
            self.meeting.group_roles.filter(
                role_id__in=[DELEGAT, DELEGAT_FULLMAKT, SUPPLEANT]
            ).order_by("role_id")
        )
        if len(relevant_roles) != 3:
            raise ElectoralRegisterError(
                "Bad configuration, wrong roles returned. This should never be used without the correct meeting dialect."
            )
        role_delegat: GroupRole = relevant_roles[0]
        role_delegat_fullmakt: GroupRole = relevant_roles[1]
        role_suppleant: GroupRole = relevant_roles[2]
        groups_with_votes = self.meeting.groups.filter(votes__gt=0)
        potential_voters = self.meeting.roles.filter(
            assigned__contains=ROLE_POTENTIAL_VOTER
        ).values_list("user_id", flat=True)
        if active_enabled_for_meeting(self.meeting):
            potential_voters = self.meeting.active_users.filter(
                user_id__in=potential_voters
            ).values_list("user_id", flat=True)
        base_gm_qs = GroupMembership.objects.filter(
            meeting_group__in=groups_with_votes, user_id__in=potential_voters
        )
        gm_fullmakt_qs = base_gm_qs.filter(role=role_delegat_fullmakt)
        gm_delegatt_qs = base_gm_qs.filter(role=role_delegat)
        gm_suppleant_qs = base_gm_qs.filter(role=role_suppleant)
        group_vote_power = {x.pk: x.votes for x in groups_with_votes}
        picked_primary_voters: set[int] = set()
        # First iteration - only ordinary
        self.iterate_and_pick_voters(
            group_vote_power, gm_fullmakt_qs, picked_primary_voters
        )
        self.iterate_and_pick_voters(
            group_vote_power, gm_delegatt_qs, picked_primary_voters
        )
        # Secondary for ordinaries first
        picked_secondary_voters: set[int] = set()
        self.iterate_and_pick_voters(
            group_vote_power, gm_fullmakt_qs, picked_secondary_voters
        )
        self.iterate_and_pick_voters(
            group_vote_power, gm_delegatt_qs, picked_secondary_voters
        )
        # And then fill substitutes (suppleant)
        self.iterate_and_pick_voters(
            group_vote_power, gm_suppleant_qs, picked_primary_voters
        )
        self.iterate_and_pick_voters(
            group_vote_power, gm_suppleant_qs, picked_secondary_voters
        )
        voters = {x: 1 for x in picked_primary_voters}
        voters.update({x: 2 for x in picked_secondary_voters})
        return voters

    def pre_apply(self, poll: Poll):
        self.create_er()  # Won't trigger unless needed
