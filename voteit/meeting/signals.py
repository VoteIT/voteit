from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import m2m_changed
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.db.models.signals import pre_save
from django.dispatch import Signal
from django.dispatch import receiver
from voteit.messaging.channels import UserChannel

from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.core.messages.role_updates import RolesChanged
from voteit.core.messages.role_updates import RolesRemoved
from voteit.core.role import Role
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import broadcast_meeting
from voteit.meeting.messages import GroupMembershipChanged
from voteit.meeting.messages import GroupMembershipDeleted
from voteit.meeting.messages import GroupRoleChanged
from voteit.meeting.messages import GroupRoleDeleted
from voteit.meeting.messages import MeetingChanged
from voteit.meeting.messages import MeetingDeleted
from voteit.meeting.messages import MeetingGroupChanged
from voteit.meeting.messages import MeetingGroupDeleted
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.rest_api.serializers import GroupMembershipSerializer
from voteit.meeting.rest_api.serializers import GroupRoleSerializer
from voteit.meeting.rest_api.serializers import MeetingDetailSerializer
from voteit.meeting.rest_api.serializers import MeetingGroupSerializer

if TYPE_CHECKING:
    from voteit.core.abcs import MeetingContext

# Signal providing an atomic transaction to do cleanup when a meeting is archived
# Will provide argument "meeting"
archive_meeting = Signal()

# Meeting joined signal, whenever a user gets roles within a meeting
# hook this up to other things that needs to be checked, for instance if there's an unused invite
# Arguments
#   meeting
#   user
#   meeting_roles (Meeting roles object)
meeting_joined = Signal()

# When electoral register changes for an existing meeting, we sometimes need to do other updates.
# This should be handled within a transaction.
er_policy_changed = Signal()
# Arguments
#   instance: ElectoralRegisterPolicy
#   sender: type[ElectoralRegisterPolicy]


# Signal when group role is added/removed through a GroupMembership object
#   instance:GroupMembership
#   role:GroupRole
group_role_added = Signal()
group_role_removed = Signal()


_del_msg_class = {
    Meeting: MeetingDeleted,
    MeetingGroup: MeetingGroupDeleted,
    GroupRole: GroupRoleDeleted,
    GroupMembership: GroupMembershipDeleted,
}
# There is no longer an "added" message distinct from "changed", and the
# serializers were already the same for both, so one mapping covers each.
_serializer_class = {
    MeetingGroup: MeetingGroupSerializer,
    GroupRole: GroupRoleSerializer,
    GroupMembership: GroupMembershipSerializer,
}
_msg_class = {
    MeetingGroup: MeetingGroupChanged,
    GroupRole: GroupRoleChanged,
    GroupMembership: GroupMembershipChanged,
}


@receiver(post_save, sender=MeetingRoles)
@disable_on_raw_save
@on_transaction_commit
def meeting_roles_created(instance: MeetingRoles, created: bool = None, **kw):
    """
    Note! This is only run after transaction commits, and it creates a new transaction.
    Why the fuzz? Since we don't know where the role creation originated we need to make sure that any other
    adjustments will be complete. (Like marking an invite as accepted)
    """

    if created:
        with transaction.atomic(durable=True):
            meeting_joined.send(
                sender=MeetingRoles,
                meeting=instance.meeting,
                user=instance.user,
                meeting_roles=instance,
            )


@receiver(pre_delete, sender=MeetingRoles)
@disable_on_raw_save
def remove_group_memberships(instance: MeetingRoles, **kw):
    GroupMembership.objects.filter(
        meeting_group__meeting_id=instance.context_id, user_id=instance.user_id
    ).delete()


@receiver(post_save, sender=Meeting)
@disable_on_raw_save
def meeting_change(instance, created=None, **kw):
    if not created:
        data = MeetingDetailSerializer(instance).data
        msg = MeetingChanged(payload=data)
        broadcast_meeting(instance, msg)


@receiver(pre_delete, sender=Meeting)
@receiver(pre_delete, sender=MeetingGroup)
@receiver(pre_delete, sender=GroupRole)
@receiver(pre_delete, sender=GroupMembership)
def publish_deleted_to_meeting(instance: MeetingContext, *, sender, **kwargs):
    if instance.meeting and instance.pk is not None:
        msg_class = _del_msg_class.get(sender)
        msg = msg_class(payload={"pk": instance.pk})
        broadcast_meeting(instance.meeting, msg, on_commit=True)


@receiver(post_save, sender=MeetingGroup)
@receiver(post_save, sender=GroupMembership)
@receiver(post_save, sender=GroupRole)
@disable_on_raw_save
def context_changed_publish_to_meeting(instance, *, sender, **kwargs):
    data = _serializer_class[sender](instance).data
    if sender is GroupMembership:
        data["m"] = instance.meeting.pk
    msg = _msg_class[sender](payload=data)
    broadcast_meeting(instance.meeting, msg, on_commit=True)


@receiver(pre_save, sender=MeetingGroup)
@disable_on_raw_save
def adjust_membership_voting_power_when_group_changes(*, instance: MeetingGroup, **kw):
    if instance.pk:
        # We only care about updates here!
        qs = instance.memberships.filter(votes__gt=0)
        must_clear = True
        if instance.votes:
            votesum = qs.aggregate(Sum("votes"))["votes__sum"]
            if votesum and votesum <= instance.votes:
                must_clear = False
        if must_clear:
            # We only need to clear votes if their sum is higher than assigned total
            for membership in qs:
                membership.votes = None
                membership.save()


def _role_msg_publish(instance: MeetingRoles, msg):
    broadcast_meeting(instance.meeting, msg)
    # FIXME: Duplicate message to user, but we might not send to meeting later on
    # This is a temporary thing
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.sync_publish(msg)


@receiver(roles_added, sender=MeetingRoles)
@disable_on_raw_save
def push_roles_added(instance: MeetingRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesChanged(
            payload={
                "roles": roles,
                "pk": instance.context.pk,
                "model": get_model_shortname(instance.context),
                "user_pk": instance.user.pk,
            }
        ),
    )


@receiver(roles_removed, sender=MeetingRoles)
def push_roles_removed(instance: MeetingRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesRemoved(
            payload={
                "roles": roles,
                "pk": instance.context.pk,
                "model": get_model_shortname(instance.context),
                "user_pk": instance.user.pk,
            }
        ),
    )


@receiver(post_save, sender=GroupMembership)
def delegate_signal_role_added(instance: GroupMembership, created: bool, **kwargs):
    """
    Delegate single creation to role_added. Updated GroupMembership objects should manually trigger this.
    """
    if created and instance.role is not None:
        instance.signal_role_added()


@receiver(pre_delete, sender=GroupMembership)
def delegate_signal_role_deleted(instance: GroupMembership, **kwargs):
    """
    Delegate single deleted GroupMembership to signal role_removed
    """
    if instance.role is not None:
        instance.signal_role_removed()


@receiver(group_role_added, sender=GroupMembership)
@disable_on_raw_save  # Imports will contain rolemap already
def handle_meeting_roles_through_role_added(
    instance: GroupMembership, role: GroupRole, **kwargs
):
    """
    A user was assigned a role through group membership.
    This simply adds meeting roles which will trigger event if needed.
    """
    if role.roles:
        instance.meeting.add_roles(instance.user, *role.roles)


@receiver(group_role_removed, sender=GroupMembership)
def handle_meeting_roles_through_removed(
    instance: GroupMembership, role: GroupRole, **kwargs
):
    """
    This signal is triggered when a role will be removed from GroupMembership.
    So any checks regarding role must assume the group membership object still exists.
    """
    maybe_remove_meeting_roles = set(role.roles)
    if not maybe_remove_meeting_roles:
        return  # Nothing to do
    meeting = instance.meeting
    meeting_group = instance.meeting_group
    if not meeting.group_roles_active:
        return  # Don't check for this meeting
    memberships = GroupMembership.objects.filter(
        user=instance.user, meeting_group__meeting=meeting, role__isnull=False
    ).exclude(meeting_group=meeting_group)
    for member in memberships:
        maybe_remove_meeting_roles = maybe_remove_meeting_roles - set(member.role.roles)
        if not maybe_remove_meeting_roles:
            return  # Potential remove roles exhausted
    meeting.remove_roles(instance.user, *maybe_remove_meeting_roles)


@receiver(m2m_changed, sender=MeetingGroup.members.through)
def compat_m2m_publish_group_membership(
    *, instance, action: str, reverse: bool, model: type, pk_set, using, **kwargs
):
    """
    This little nugget delegates m2m interactions so the through model gets proper post_save / pre_delete signals since
    we rely on them. It's probably a bad idea to handle it this way, but I see no other option.
    """
    through = MeetingGroup.members.through
    if action == "post_add":
        if reverse:
            for obj in through.objects.filter(
                meeting_group__pk__in=pk_set, user=instance
            ).prefetch_related("role"):
                post_save.send(
                    sender=through,
                    instance=obj,
                    created=True,
                    using=using,
                )
        else:
            for obj in through.objects.filter(
                user__pk__in=pk_set, meeting_group=instance
            ).prefetch_related("role"):
                post_save.send(
                    sender=through,
                    instance=obj,
                    created=True,
                    using=using,
                )


# Remove signals are sent another way, so they're actually caught the expected way
# elif action == "pre_remove":
#     if reverse:
#         for obj in through.objects.filter(
#             meeting_group__pk__in=pk_set, user=instance
#         ):
#             pre_delete.send(
#                 sender=through,
#                 instance=obj,
#                 using=using,
#             )
#     else:
#         for obj in through.objects.filter(
#             user__pk__in=pk_set, meeting_group=instance
#         ):
#             pre_delete.send(
#                 sender=through,
#                 instance=obj,
#                 using=using,
#             )
