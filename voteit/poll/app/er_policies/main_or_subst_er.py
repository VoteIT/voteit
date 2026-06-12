from __future__ import annotations

from collections import defaultdict
from logging import getLogger
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from voteit.active.utils import active_enabled_for_meeting
from voteit.meeting.models import GroupMembership
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.exceptions import ElectoralRegisterError
from voteit.poll.registries import er_policy

if TYPE_CHECKING:
    from voteit.poll.models import Poll

__all__ = ("MainSubstActivePolicy",)

logger = getLogger(__name__)
User = get_user_model()

MAIN_ROLE_ID = "main"
SUBSTITUTE_ROLE_ID = "substitute"


@er_policy
class MainSubstActivePolicy(ElectoralRegisterPolicy):
    """
    Instructions:
    - Set total number of votes on a group.
    - Set role main or substitute on members of that group. (That should trigger potential voter too)
    - Users set themselves as active.
    - When a poll starts or becomes upcoming, the main users get one vote each, if there are any spare
    votes left they're distributed to substitutes in chronological order of when they became active.
    """

    name = "main_subst_active"
    title = _("Main/Substitute + active")
    description = _(
        "Voters assigned depending on number of votes in groups. Votes are assigned to main first, "
        "then substitutes if there are any left. "
        "If there aren't enough votes for everyone, "
        "they're assigned in the order of when users became active. "
        "Electoral registries will be created and assigned when a poll starts."
    )
    logger = logger
    handles_vote_weight = False
    available = False  # Not installed manually
    allow_trigger = True
    handles_active_check = True

    def get_voters(self, update_memberships=False, **kwargs) -> dict[int, int]:
        relevant_roles = list(
            self.meeting.group_roles.filter(
                role_id__in=[MAIN_ROLE_ID, SUBSTITUTE_ROLE_ID]
            ).order_by("role_id")
        )
        if len(relevant_roles) != 2:
            raise ElectoralRegisterError(
                "Bad configuration, wrong roles returned. This should never be used without the correct meeting dialect."
            )
        main_role, subst_role = relevant_roles
        # Preload active users, if enabled
        if active_enabled_for_meeting(meeting=self.meeting):
            active_user_pks = list(
                self.meeting.active_users.order_by("created").values_list(
                    "user_id", flat=True
                )
            )
            user_order = {pk: i for i, pk in enumerate(active_user_pks)}
        else:
            # We have no way of knowing order, using pk is as bad as any other method...?
            user_order = {
                pk: pk for pk in self.meeting.participants.values_list("pk", flat=True)
            }
        # Prefetch memberships once with the required filters
        membership_qs = GroupMembership.objects.filter(
            user_id__in=user_order,
            role_id__in=[main_role.id, subst_role.id],
        ).select_related("user", "role")
        groups_with_votes = self.meeting.groups.filter(votes__gt=0).prefetch_related(
            models.Prefetch("memberships", queryset=membership_qs)
        )
        group_vote_power = {g: g.votes for g in groups_with_votes}
        # Lookup-dict
        # Structure: { group.pk: { role_id: [user_id, ...] } }
        group_memberships = defaultdict(lambda: defaultdict(list))
        for g in groups_with_votes:
            for m in g.memberships.all():
                group_memberships[g.pk][m.role_id].append(m.user_id)
        # Sort each membership list once using the precomputed order
        for gpk in group_memberships:
            for role_id in group_memberships[gpk]:
                group_memberships[gpk][role_id].sort(key=lambda pk: user_order[pk])
        # Avoid queries during loop
        groups_vote_dist = defaultdict(set)
        picked_voters: set[int] = set()
        for role in [main_role, subst_role]:
            for group in groups_with_votes:
                # If exhausted
                if not group_vote_power[group]:
                    continue
                members = group_memberships[group.pk].get(role.id, [])
                for user_pk in members:
                    if not group_vote_power[group]:
                        break
                    if user_pk in picked_voters:
                        continue
                    # User should be voter
                    picked_voters.add(user_pk)
                    group_vote_power[group] -= 1
                    groups_vote_dist[group].add(user_pk)

        # And finally update GroupMembership objects vote distribution (to signal why a user has a vote)
        if update_memberships:
            for group, user_pks in groups_vote_dist.items():
                # Needs to have a vote
                for membership in group.memberships.filter(
                    user_id__in=user_pks
                ).exclude(votes=1):
                    membership.votes = 1
                    membership.save()
                # Should not have a vote
                for membership in group.memberships.exclude(
                    user_id__in=user_pks
                ).filter(votes__isnull=False):
                    # Update this (slow) way to trigger events - can be optimized later on
                    membership.votes = None
                    membership.save()
            # Make sure no other groups have votes
            for membership in GroupMembership.objects.filter(
                meeting_group__meeting=self.meeting, votes__gt=0
            ).exclude(meeting_group__in=groups_vote_dist.keys()):
                # Update this (slow) way to trigger events - can be optimized later on
                membership.votes = None
                membership.save()
        return {x: 1 for x in picked_voters}

    def pre_apply(self, poll: Poll):
        self.create_er()  # Won't trigger unless needed
