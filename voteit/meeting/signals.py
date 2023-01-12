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
from envelope.app.user_channel.channel import UserChannel
from envelope.signals import channel_subscribed

from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.core.messages.role_updates import RolesAdded
from voteit.core.messages.role_updates import RolesRemoved
from voteit.core.role import Role
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.messages import GroupMembershipAdded
from voteit.meeting.messages import GroupMembershipChanged
from voteit.meeting.messages import GroupMembershipDeleted
from voteit.meeting.messages import GroupRoleAdded
from voteit.meeting.messages import GroupRoleChanged
from voteit.meeting.messages import GroupRoleDeleted
from voteit.meeting.messages import MeetingChanged
from voteit.meeting.messages import MeetingDeleted
from voteit.meeting.messages import MeetingGroupAdded
from voteit.meeting.messages import MeetingGroupChanged
from voteit.meeting.messages import MeetingGroupDeleted
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.models import MeetingGroup
from voteit.meeting.rest_api.serializers import GroupMembershipSerializer
from voteit.meeting.rest_api.serializers import GroupRoleSerializer
from voteit.meeting.rest_api.serializers import MeetingDetailSerializer
from voteit.meeting.rest_api.serializers import MeetingGroupSerializer
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.utils import AppState
    from voteit.core.abcs import MeetingContext
    from voteit.messaging.base import BaseObjectAdded
    from voteit.messaging.base import BaseObjectChanged
    from voteit.messaging.base import BaseObjectDeleted
    from rest_framework.serializers import ModelSerializer

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


def mk_default_changed_publisher_to_meeting(
    *,
    model: type[MeetingContext],
    added_serializer: type[ModelSerializer],
    changed_serializer: type[ModelSerializer],
    added_msg: type[BaseObjectAdded],
    changed_msg: type[BaseObjectChanged],
):
    @receiver(post_save, sender=model)
    @disable_on_raw_save
    def _publish_changed(*, instance: model, created: bool, **kw):
        f"""
        Default publish changed for {model}
        """
        meeting_ch = MeetingChannel.from_instance(instance.meeting)
        if created:
            data = added_serializer(instance).data
            msg = added_msg(**data)
        else:
            data = changed_serializer(instance).data
            msg = changed_msg(**data)
        meeting_ch.sync_publish(msg, on_commit=True)


def mk_default_deleted_publisher_to_meeting(
    *,
    model: type[MeetingContext],
    msg_class: type[BaseObjectDeleted],
):
    @disable_on_raw_save
    @receiver(pre_delete, sender=model)
    def _publish_delete(*, instance: model, **kwargs):
        f"""
        Default publish deleted for {model}
        """
        meeting_ch = MeetingChannel.from_instance(instance.meeting)
        msg = msg_class(pk=instance.pk)
        meeting_ch.sync_publish(msg, on_commit=True)


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


@receiver(post_save, sender=Meeting)
@disable_on_raw_save
def meeting_change(instance, created=None, **kw):
    if not created:
        data = MeetingDetailSerializer(instance).data
        ch = MeetingChannel.from_instance(instance)
        msg = MeetingChanged(data=data)
        ch.sync_publish(msg)


mk_default_deleted_publisher_to_meeting(model=Meeting, msg_class=MeetingDeleted)


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send users meeting roles as response
    """
    roles = context.get_roles(user)
    if roles:
        msg = RolesAdded(
            roles=context.roles_to_strings(*roles),
            pk=context.pk,
            model=get_model_shortname(context),
            user_pk=user.pk,
        )
        app_state.append(msg)
    # Append all groups - members have moved to GroupMembership!
    meeting_groups_qs = context.groups.all().prefetch_related("mentions", "memberships")
    app_state.append_from_queryset(
        meeting_groups_qs,
        MeetingGroupSerializer,
        MeetingGroupAdded,
    )
    # GroupMemberships - these are prefetched so impact should be minimal
    items = set()
    for mg in meeting_groups_qs:
        items.update(mg.memberships.all())
    app_state.append_from_queryset(
        items,
        GroupMembershipSerializer,
        GroupMembershipAdded,
    )
    # And GroupRoles
    app_state.append_from_queryset(
        context.group_roles.all(),
        GroupRoleSerializer,
        GroupRoleAdded,
    )


# MeetingGroup
mk_default_changed_publisher_to_meeting(
    model=MeetingGroup,
    added_serializer=MeetingGroupSerializer,
    changed_serializer=MeetingGroupSerializer,
    added_msg=MeetingGroupAdded,
    changed_msg=MeetingGroupChanged,
)
mk_default_deleted_publisher_to_meeting(
    model=MeetingGroup,
    msg_class=MeetingGroupDeleted,
)


# GroupRole
mk_default_changed_publisher_to_meeting(
    model=GroupRole,
    added_serializer=GroupRoleSerializer,
    changed_serializer=GroupRoleSerializer,
    added_msg=GroupRoleAdded,
    changed_msg=GroupRoleChanged,
)
mk_default_deleted_publisher_to_meeting(
    model=GroupRole,
    msg_class=GroupRoleDeleted,
)


# GroupMembership
mk_default_changed_publisher_to_meeting(
    model=GroupMembership,
    added_serializer=GroupMembershipSerializer,
    changed_serializer=GroupMembershipSerializer,
    added_msg=GroupMembershipAdded,
    changed_msg=GroupMembershipChanged,
)
mk_default_deleted_publisher_to_meeting(
    model=GroupMembership,
    msg_class=GroupMembershipDeleted,
)


@receiver(pre_save, sender=MeetingGroup)
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
    meeting_ch = MeetingChannel.from_instance(instance.meeting)
    meeting_ch.sync_publish(msg)
    # FIXME: Duplicate message to user, but we might not send to meeting later on
    # This is a temporary thing
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.sync_publish(msg)


@receiver(roles_added, sender=MeetingRoles)
@disable_on_raw_save
def push_roles_added(instance: MeetingRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesAdded(
            roles=instance.context.roles_to_strings(*roles),
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )


@receiver(roles_removed, sender=MeetingRoles)
def push_roles_removed(instance: MeetingRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesRemoved(
            roles=instance.context.roles_to_strings(*roles),
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )


def _check_roles(user, meeting, excluding_membership: int | None = None):
    # FIXME: This should be optimized
    if meeting.group_roles_active:
        assigned = set()
        qs = GroupMembership.objects.filter(
            user=user, meeting_group__meeting=meeting, role__isnull=False
        )
        if excluding_membership:
            qs = qs.exclude(pk=excluding_membership)
        for membership in qs.select_related("role"):
            assigned.update(membership.role.roles)
        to_remove = {
            ROLE_POTENTIAL_VOTER,
            ROLE_DISCUSSER,
            ROLE_PROPOSER,
        } - assigned
        meeting.remove_roles(user, *to_remove)
        meeting.add_roles(user, *assigned)


@receiver(post_save, sender=GroupMembership)
def membership_changed(instance: GroupMembership, **kwargs):
    _check_roles(instance.user, instance.meeting_group.meeting)


@receiver(pre_delete, sender=GroupMembership)
def membership_deleted(instance: GroupMembership, **kwargs):
    _check_roles(
        instance.user, instance.meeting_group.meeting, excluding_membership=instance.pk
    )


@receiver(post_save, sender=GroupRole)
def group_role_changed_ck_roles(instance: GroupRole, **kwargs):
    for gm in GroupMembership.objects.filter(role=instance).prefetch_related(
        "user", "meeting_group", "meeting_group__meeting"
    ):
        # FIXME: Optimize, this will be quite slow in large meetings
        _check_roles(gm.user, gm.meeting_group.meeting)


@receiver(m2m_changed, sender=MeetingGroup.members.through)
def compat_m2m_publish_group_membership(
    *, instance, action: str, reverse: bool, model: type, pk_set, using, **kwargs
):
    """
    This little nugget delegates m2m interactions so the through model gets proper post_save / pre_delete signals since
    we rely on them. It's probably a bad idea to handle it this way, but i see no other option.
    """
    through = MeetingGroup.members.through
    if action == "post_add":
        if reverse:
            for obj in through.objects.filter(
                meeting_group__pk__in=pk_set, user=instance
            ):
                post_save.send(
                    sender=through,
                    instance=obj,
                    created=True,
                    using=using,
                )
        else:
            for obj in through.objects.filter(
                user__pk__in=pk_set, meeting_group=instance
            ):
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
