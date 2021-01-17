from typing import Optional

from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.db.models.signals import post_delete
from django.dispatch import receiver
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.messaging.channels.user import UserChannel
from voteit.messaging.signals import channel_subscribed
from voteit.presence import messages

from voteit.presence.messages import (
    PresenceCheckStatus,
    PresenceDeleted,
    PresenceCheckAdded,
    PresenceCheckChanged,
    PresenceCheckDeleted,
)
from voteit.presence.messages import PresenceAdded

from voteit.presence.models import Presence
from voteit.presence.models import PresenceCheck
from voteit.presence.channels import PresenceCheckChannel
from voteit.presence.rest_api.serializers import PresenceDetailSerializer
from voteit.presence.rest_api.serializers import PresenceCheckDetailSerializer


@receiver(post_save, sender=Presence)
def presence_added(instance=None, created: bool = None, **kw):
    """ Send presence item to user channel and a count to the specific presence check channel.
    """
    if created:
        # There is no change for presence that's relevant
        user_ch = UserChannel.from_instance(instance.user)
        data = PresenceDetailSerializer(instance).data
        msg = PresenceCheckStatus(
            pk=instance.presence_check.pk,
            present=instance.presence_check.presences.count(),
        )
        ch = PresenceCheckChannel.from_instance(instance.presence_check)
        ch.publish(msg)
        # And the users message
        presence_msg = PresenceAdded(**data)
        user_ch.publish(presence_msg)


@receiver(post_delete, sender=Presence)
def presence_deleted(instance: Presence = None, **kw):
    """ Notify of removed presence item to user channel and a count to the specific presence check channel.
    """
    msg = PresenceCheckStatus(
        pk=instance.presence_check.pk, present=instance.presence_check.presences.count()
    )
    ch = PresenceCheckChannel.from_instance(instance.presence_check)
    ch.publish(msg)
    presence_msg = PresenceDeleted(pk=instance.pk)
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.publish(presence_msg)


@receiver(post_save, sender=PresenceCheck)
def presence_check_changed(instance: PresenceCheck = None, created: bool = None, **kw):
    """ Transmit presence check to meeting channel
    """
    meeting = instance.presence_system.meeting
    if meeting is not None:
        data = PresenceCheckDetailSerializer(instance).data
        if created:
            msg = PresenceCheckAdded(**data)
        else:
            msg = PresenceCheckChanged(**data)
        ch = MeetingChannel.from_instance(meeting)
        ch.publish(msg)


@receiver(post_delete, sender=PresenceCheck)
def presence_check_deleted(instance=None, **kw):
    """ Transmit that presence check has been deleted to meeting channel.
    """
    meeting = instance.presence_system.meeting
    if meeting is not None:
        msg = PresenceCheckDeleted(pk=instance.pk)
        ch = MeetingChannel.from_instance(meeting)
        ch.publish(msg)


@receiver(channel_subscribed, sender=MeetingChannel)
def channel_subscribed(channel: MeetingChannel, user: AbstractUser, app_state: list, **kw):
    meeting: Meeting = channel.context
    if presence_check := meeting.presencesystem.presence_checks.latest_open():
        data = PresenceCheckDetailSerializer(presence_check).data
        app_state.append(PresenceCheckAdded(**data).app_state)
        if user_presence := presence_check.presences.filter(user=user).first():
            data = PresenceDetailSerializer(user_presence).data
            app_state.append(PresenceAdded(**data).app_state)
