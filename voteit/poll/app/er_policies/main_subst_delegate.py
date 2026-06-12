from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import models
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.signals import group_role_added
from voteit.meeting.signals import group_role_removed
from voteit.poll.abcs import ElectoralRegisterPolicy
from voteit.poll.abcs import VoteTransferPolicy
from voteit.poll.models import VoteTransfer
from voteit.poll.registries import er_policy
from voteit.poll.registries import vote_transfer_policies

if TYPE_CHECKING:
    from voteit.poll.models import Poll

__all__ = (
    "MainAndSubstVT",
    "MainSubstDelegatePolicy",
)

logger = getLogger(__name__)
User = get_user_model()

MAIN_ROLE_ID = "main"
SUBSTITUTE_ROLE_ID = "substitute"

if TYPE_CHECKING:
    from voteit.core.models import User


@vote_transfer_policies
class MainAndSubstVT(VoteTransferPolicy):
    """
    Allow transfer of vote power from potential voter with role main to subst_role
    """

    name = "main_and_subst"

    def check(self, source: User, target: User, modifying: VoteTransfer | None = None):
        # We only have to check source user if it's new - and source already has a unique check
        qs = self.meeting.vote_transfers
        if modifying:
            qs = qs.exclude(pk=modifying.pk)
        if qs.filter(models.Q(target=target) | models.Q(source=target)).exists():
            raise ValidationError(
                {
                    "target": f"User {target} already delegates their vote or has received a vote from someone else."
                }
            )
        # Target may never be main in another group
        if self.meeting.groups.filter(
            memberships__user=target, memberships__role__role_id=MAIN_ROLE_ID
        ).exists():
            raise ValidationError(
                {
                    "target": "Target user is already a main delegate, maybe within another group?"
                }
            )
        # Source and target must have intersecting groups
        if (
            not self.meeting.groups.filter(
                memberships__user=source, memberships__role__role_id=MAIN_ROLE_ID
            )
            .filter(
                memberships__user=target, memberships__role__role_id=SUBSTITUTE_ROLE_ID
            )
            .exists()
        ):
            raise ValidationError(
                {
                    "target": "Source and target user must have roles within the same group."
                }
            )


@er_policy
class MainSubstDelegatePolicy(ElectoralRegisterPolicy):
    """
    Main role users have votes and can delegate them to subst.

    """

    name = "main_subst_delegate"
    title = _("Main/Substitute + delegate votes")
    description = _(
        "Group members with main have votes and can delegate them to users with substitute role. "
        "Electoral registries will be created and assigned when a poll starts."
    )
    logger = logger
    handles_vote_weight = False
    available = False  # Not installed manually
    allow_trigger = True
    handles_active_check = False
    vote_transfer_policy = MainAndSubstVT.name

    def get_voters(self, update_memberships=False, **kwargs) -> dict[int, int]:
        voters = set(
            self.meeting.groups.filter(
                memberships__role__role_id=MAIN_ROLE_ID
            ).values_list("memberships__user_id", flat=True)
        )
        for vt in self.meeting.vote_transfers.filter(source_id__in=voters):
            voters.add(vt.target_id)
            voters.remove(vt.source_id)
        return {x: 1 for x in voters}

    def pre_apply(self, poll: Poll):
        self.create_er()  # Won't trigger unless needed


@receiver(group_role_added)
def check_role_added(*, instance: GroupMembership, role: GroupRole, **kwargs):
    meeting = instance.meeting
    if not isinstance(meeting.vote_transfer_policy, MainAndSubstVT):
        return
    # If target received main role, remove any active transfers
    if role.role_id == MAIN_ROLE_ID:
        meeting.vote_transfers.filter(target_id=instance.user_id).delete()


@receiver(group_role_removed)
def check_role_removed(*, instance: GroupMembership, role: GroupRole, **kwargs):
    meeting = instance.meeting
    if not isinstance(meeting.vote_transfer_policy, MainAndSubstVT):
        return
    if role.role_id == MAIN_ROLE_ID:
        # First, check if there are any other main roles, if not, we can safely delete.
        # But we only need to care if there's an existing vote transfer. In this dialect, it may only be one.
        if vt := meeting.vote_transfers.filter(source_id=instance.user_id).first():
            if GroupMembership.objects.filter(
                user_id=vt.target_id,
                role__role_id=SUBSTITUTE_ROLE_ID,
                meeting_group_id=instance.meeting_group_id,
            ).exists():
                # Main was removed from intersecting group
                vt.delete()
    elif role.role_id == SUBSTITUTE_ROLE_ID:
        # Are there any relevant transfers?
        if vt := meeting.vote_transfers.filter(target_id=instance.user_id).first():
            # Do the users belong to this group?
            if GroupMembership.objects.filter(
                user_id=vt.source_id,
                role__role_id=MAIN_ROLE_ID,
                meeting_group_id=instance.meeting_group_id,
            ).exists():
                # Subst was removed from intersecting group
                vt.delete()
