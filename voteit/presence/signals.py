from __future__ import annotations
from contextlib import suppress
from typing import TYPE_CHECKING

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from envelope.app.user_channel.channel import UserChannel
from envelope.signals import channel_subscribed

from voteit.core.decorators import disable_on_raw_save
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.presence.channels import PresenceCheckChannel
from voteit.presence.messages import PresenceAdded
from voteit.presence.messages import PresenceCheckAdded
from voteit.presence.messages import PresenceCheckChanged
from voteit.presence.messages import PresenceCheckDeleted
from voteit.presence.messages import PresenceDeleted
from voteit.presence.models import Presence
from voteit.presence.models import PresenceCheck
from voteit.presence.rest_api.serializers import PresenceCheckDetailSerializer
from voteit.presence.rest_api.serializers import PresenceDetailSerializer

if TYPE_CHECKING:
    from envelope.channels.models import AppState


@receiver(post_save, sender=Presence)
@disable_on_raw_save
def presence_added(instance: Presence, created: bool = None, **kw):
    """
    Send presence item to user channel and a count to the specific presence check channel.
    """
    if created:
        _publish_presence_changed(presence=instance, present=True)


@receiver(pre_delete, sender=Presence)
def presence_deleted(instance: Presence, **kw):
    """
    Notify of removed presence item to user channel and a count to the specific presence check channel.
    """
    _publish_presence_changed(presence=instance, present=False)


def _publish_presence_changed(*, presence: Presence, present: bool):
    data = PresenceDetailSerializer(presence).data
    if present:
        msg = PresenceAdded(**data)
    else:
        msg = PresenceDeleted(**data)
    ch = PresenceCheckChannel.from_instance(presence.presence_check)
    ch.sync_publish(msg)
    user_ch = UserChannel.from_instance(presence.user)
    user_ch.sync_publish(msg)


@receiver(post_save, sender=PresenceCheck)
@disable_on_raw_save
def presence_check_changed(instance: PresenceCheck = None, created: bool = None, **kw):
    """Transmit presence check to meeting channel"""
    meeting = instance.meeting
    if meeting is not None:
        data = PresenceCheckDetailSerializer(instance).data
        if created:
            msg = PresenceCheckAdded(**data)
        else:
            msg = PresenceCheckChanged(**data)
        ch = MeetingChannel.from_instance(meeting)
        ch.sync_publish(msg)


@receiver(post_delete, sender=PresenceCheck)
def presence_check_deleted(instance=None, **kw):
    """
    Transmit that presence check has been deleted to meeting channel.
    """
    meeting = instance.meeting
    if meeting is not None:
        msg = PresenceCheckDeleted(pk=instance.pk)
        ch = MeetingChannel.from_instance(meeting)
        ch.sync_publish(msg)


@receiver(channel_subscribed, sender=MeetingChannel)
def _channel_subscribed(
    context: Meeting, user: AbstractUser, app_state: AppState, **kw
):
    """
    Populate app_state with current, if any, presence check objects.
    """
    with suppress(ObjectDoesNotExist):
        if presence_check := context.presence_checks.latest_open():
            app_state.append(
                PresenceCheckAdded(**PresenceCheckDetailSerializer(presence_check).data)
            )
            if user_presence := presence_check.presences.filter(user=user).first():
                app_state.append(
                    PresenceAdded(**PresenceDetailSerializer(user_presence).data)
                )


@receiver(channel_subscribed, sender=PresenceCheckChannel)
def _check_channel_subscribed(
    context: PresenceCheck, user: AbstractUser, app_state: AppState, **kw
):
    """
    Since this sends out who's present, it has restricted access.
    """
    qs = context.presences.all()
    for item in PresenceDetailSerializer(qs, many=True).data:
        app_state.append(PresenceAdded(**item))
