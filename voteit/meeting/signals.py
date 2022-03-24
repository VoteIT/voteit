from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
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
from voteit.meeting.messages import MeetingChanged
from voteit.meeting.messages import MeetingGroupAdded
from voteit.meeting.messages import MeetingGroupChanged
from voteit.meeting.messages import MeetingGroupDeleted
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.models import MeetingGroup
from voteit.meeting.rest_api.serializers import MeetingDetailSerializer
from voteit.meeting.rest_api.serializers import MeetingGroupSerializer


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.utils import AppState


# Signal providing an atomic transaction to do cleanup when a meeting is archived
archive_meeting = Signal(providing_args=["meeting"])


# FIXME: What about deleted? Some kind of crash and burn message?
@receiver(post_save, sender=Meeting)
@disable_on_raw_save
def meeting_change(instance, created=None, **kw):
    if not created:
        data = MeetingDetailSerializer(instance).data
        ch = MeetingChannel.from_instance(instance)
        msg = MeetingChanged(data=data)
        ch.sync_publish(msg)


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
            mm=dict(),
            roles=context.roles_to_strings(*roles),
            pk=context.pk,
            model=get_model_shortname(context),
            user_pk=user.pk,
        )
        app_state.append(msg)
    # Append all groups
    app_state.append_from_queryset(
        context.groups.all(), MeetingGroupSerializer, MeetingGroupAdded
    )


@receiver(post_save, sender=MeetingGroup)
@disable_on_raw_save
@on_transaction_commit
def meeting_group_updated(instance: MeetingGroup = None, created=None, **kw):
    meeting_ch = MeetingChannel.from_instance(instance.meeting)
    data = MeetingGroupSerializer(instance).data
    if created:
        msg = MeetingGroupAdded(**data)
    else:
        msg = MeetingGroupChanged(**data)
    meeting_ch.sync_publish(msg)


@receiver(pre_delete, sender=MeetingGroup)
def meeting_group_delete(instance=None, **kw):
    meeting_ch = MeetingChannel.from_instance(instance.meeting)
    msg = MeetingGroupDeleted(pk=instance.pk)
    meeting_ch.sync_publish(msg)


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
            mm=dict(),
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
            mm=dict(),
            roles=instance.context.roles_to_strings(*roles),
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )
