from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.core.messages import RolesAdded
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.messages import MeetingChanged
from voteit.meeting.models import Meeting
from voteit.meeting.rest_api.serializers import MeetingDetailSerializer
from voteit.messaging.signals import channel_subscribed

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.messaging.messages.app_state import AppState

# Signal providing an atomic transaction to do cleanup when a meeting is archived
archive_meeting = Signal(providing_args=["meeting"])


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


# FIXME: What about deleted? Some kind of crash and burn message?
