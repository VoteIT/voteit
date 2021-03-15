from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.core.messages import RolesAdded
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.messages import MeetingChanged
from voteit.meeting.messages import MeetingGroupAdded
from voteit.meeting.messages import MeetingGroupChanged
from voteit.meeting.messages import MeetingGroupDeleted
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.rest_api.serializers import MeetingDetailSerializer
from voteit.meeting.rest_api.serializers import MeetingGroupDetailSerializer
from voteit.messaging.signals import channel_subscribed

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.messaging.messages.app_state import AppState

# Signal providing an atomic transaction to do cleanup when a meeting is archived
archive_meeting = Signal(providing_args=["meeting"])


# FIXME: What about deleted? Some kind of crash and burn message?
@receiver(post_save, sender=Meeting)
def meeting_change(instance, created=None, **kw):
    if not created:
        data = MeetingDetailSerializer(instance).data
        ch = MeetingChannel.from_instance(instance)
        msg = MeetingChanged({}, **data)
        ch.publish(msg)


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
        context.groups.all(), MeetingGroupDetailSerializer, MeetingGroupAdded
    )


@receiver(post_save, sender=MeetingGroup)
def meeting_group_updated(instance: MeetingGroup = None, created=None, **kw):
    meeting_ch = MeetingChannel.from_instance(instance.meeting)
    data = MeetingGroupDetailSerializer(instance).data
    if created:
        msg = MeetingGroupAdded(**data)
    else:
        msg = MeetingGroupChanged(**data)
    meeting_ch.publish(msg)


@receiver(pre_delete, sender=MeetingGroup)
def meeting_group_delete(instance=None, **kw):
    meeting_ch = MeetingChannel.from_instance(instance.meeting)
    msg = MeetingGroupDeleted(pk=instance.pk)
    meeting_ch.publish(msg)
