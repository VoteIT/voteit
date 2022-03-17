from contextlib import suppress

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import receiver

from envelope.app.user_channel.channel import UserChannel
from envelope.signals import channel_subscribed
from envelope.utils import AppState
from voteit.core.decorators import disable_on_raw_save
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.presence.channels import PresenceCheckChannel
from voteit.presence.messages import PresenceAdded
from voteit.presence.messages import PresenceCheckAdded
from voteit.presence.messages import PresenceCheckChanged
from voteit.presence.messages import PresenceCheckDeleted
from voteit.presence.messages import PresenceCheckStatus
from voteit.presence.messages import PresenceDeleted
from voteit.presence.models import Presence
from voteit.presence.models import PresenceCheck
from voteit.presence.rest_api.serializers import PresenceCheckDetailSerializer
from voteit.presence.rest_api.serializers import PresenceDetailSerializer


@receiver(post_save, sender=Presence)
@disable_on_raw_save
def presence_added(instance=None, created: bool = None, **kw):
    """Send presence item to user channel and a count to the specific presence check channel."""
    if created:
        # There is no change for presence that's relevant
        user_ch = UserChannel.from_instance(instance.user)
        data = PresenceDetailSerializer(instance).data
        msg = PresenceCheckStatus(
            pk=instance.presence_check.pk,
            present=instance.presence_check.presences.count(),
        )
        ch = PresenceCheckChannel.from_instance(instance.presence_check)
        ch.sync_publish(msg)
        # And the users message
        presence_msg = PresenceAdded(**data)
        user_ch.sync_publish(presence_msg)


@receiver(post_delete, sender=Presence)
def presence_deleted(instance: Presence = None, **kw):
    """Notify of removed presence item to user channel and a count to the specific presence check channel."""
    msg = PresenceCheckStatus(
        pk=instance.presence_check.pk, present=instance.presence_check.presences.count()
    )
    ch = PresenceCheckChannel.from_instance(instance.presence_check)
    ch.sync_publish(msg)
    presence_msg = PresenceDeleted(pk=instance.pk)
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.sync_publish(presence_msg)


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
    """Transmit that presence check has been deleted to meeting channel."""
    meeting = instance.meeting
    if meeting is not None:
        msg = PresenceCheckDeleted(pk=instance.pk)
        ch = MeetingChannel.from_instance(meeting)
        ch.sync_publish(msg)


@receiver(channel_subscribed, sender=MeetingChannel)
def _channel_subscribed(
    context: Meeting, user: AbstractUser, app_state: AppState, **kw
):
    """Populate app_state with current, if any, presence check objects."""
    with suppress(ObjectDoesNotExist):
        if presence_check := context.presence_checks.latest_open():
            app_state.append_from(
                presence_check, PresenceCheckDetailSerializer, PresenceCheckAdded
            )
            if user_presence := presence_check.presences.filter(user=user).first():
                app_state.append_from(
                    user_presence, PresenceDetailSerializer, PresenceAdded
                )


@receiver(channel_subscribed, sender=PresenceCheckChannel)
def _check_channel_subscribed(
    context: PresenceCheck, user: AbstractUser, app_state: AppState, **kw
):
    app_state.append(
        PresenceCheckStatus(pk=context.pk, present=context.presences.count())
    )
