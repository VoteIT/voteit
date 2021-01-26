from __future__ import annotations

from typing import TYPE_CHECKING, Type, Optional, Union

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.speaker.messages import (
    SpeakerListOrder,
    SpeakerListChanged,
    SpeakerListAdded,
    SpeakerListDeleted,
    SpeakerSystemDeleted,
    SpeakerSystemAdded,
    SpeakerSystemChanged,
)
from voteit.speaker.models import Speaker, SpeakerList, SpeakerListSystem
from voteit.speaker.serializers import (
    SpeakerListSerializer,
    SpeakerListSystemSerializer,
)

if TYPE_CHECKING:
    pass


list_updated = Signal(providing_args=["sender", "instance"])


@receiver(post_save, sender=Speaker)
def set_initial_order(
    sender: Type[Speaker], instance: Speaker, created: bool, **kwargs
):
    """
    :param sender: Model
    :param instance: Speaker instance
    :param created: Is this a new db records? We only care about the newly created for this method.
    :param kwargs:
    """
    if created:
        sl = instance.list
        results = sl.speaker_items.filter(order__isnull=False).aggregate(
            models.Max("order")
        )
        current_order = results["order__max"]
        if current_order is None:
            order = 1
        else:
            order = current_order + 1
        instance.order = order
        instance.save()
        sl.reorder(force_signal=True)


@receiver(post_delete, sender=Speaker)
def reorder_after_delete(sender: Type[Speaker], instance: Speaker, **kwargs):
    instance.list.reorder(force_signal=True)


# FIXME: Push when active list changes
def _get_list_channel(
    speaker_list: SpeakerList,
) -> Optional[Union[MeetingChannel, AgendaItemChannel]]:
    system = speaker_list.list_system
    if system.active_list == speaker_list and system.meeting is not None:
        # We don't know of other transport ways for active list that meeting.
        # If meeting doesn't exist, we still want to default to agenda item.
        return MeetingChannel.from_instance(system.meeting)
    elif speaker_list.agenda_item is not None:
        return AgendaItemChannel.from_instance(speaker_list.agenda_item)
    return None


def _get_list_order_msg(speaker_list: SpeakerList) -> SpeakerListOrder:
    speakers_qs = speaker_list.speakers_qs().prefetch_related("user")
    users = [x.user for x in speakers_qs]
    user_pks = [x.pk for x in users]
    current = speaker_list.current and speaker_list.current.user.pk or None
    return SpeakerListOrder(pk=speaker_list.pk, queue=user_pks, current=current)


@receiver(list_updated)
def push_list_order_change(instance: SpeakerList, **kw):
    """When speakers reorder, send an update of the order.
    This is not transmitted on save for the speaker list,
    since the speaker items are separate.
    """
    channel = _get_list_channel(instance)
    if channel is not None:
        msg = _get_list_order_msg(instance)
        channel.publish(msg)


@receiver(post_save, sender=SpeakerList)
def notify_added_or_changed_speaker_list(instance: SpeakerList, created=None, **kw):
    """Send to Agenda or meeting channel depending on if it's the active list."""
    channel = _get_list_channel(instance)
    if channel is not None:
        if created:
            msg_class = SpeakerListAdded
        else:
            msg_class = SpeakerListChanged
        data = SpeakerListSerializer(instance).data
        msg = msg_class(**data)
        channel.publish(msg)


@receiver(post_delete, sender=SpeakerList)
def notify_deleted_speaker_list(instance: SpeakerList, **kw):
    channel = _get_list_channel(instance)
    if channel is not None:
        msg = SpeakerListDeleted(pk=instance.pk)
        channel.publish(msg)


@receiver(post_save, sender=SpeakerListSystem)
def notify_added_or_changed_speaker_system(
    instance: SpeakerListSystem, created=None, **kw
):
    """ Updates to speaker system, pushed to meeting channel."""
    if instance.meeting is not None:
        channel = MeetingChannel.from_instance(instance.meeting)
        if created:
            msg_class = SpeakerSystemAdded
        else:
            msg_class = SpeakerSystemChanged
        data = SpeakerListSystemSerializer(instance).data
        msg = msg_class(**data)
        channel.publish(msg)


@receiver(post_delete, sender=SpeakerListSystem)
def notify_deleted_speaker_system(instance: SpeakerListSystem, **kw):
    """ Notify meeting that the speaker system is no more."""
    if instance.meeting is not None:
        channel = MeetingChannel.from_instance(instance.meeting)
        msg = SpeakerSystemDeleted(pk=instance.pk)
        channel.publish(msg)


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """Send current state to meeting channel.
    - Speaker systems
    - Active list from each system
    - Order of any active list
    """
    systems_qs = context.speaker_systems.all()
    app_state.append_from_queryset(
        systems_qs, SpeakerListSystemSerializer, SpeakerSystemAdded
    )
    for system in systems_qs:
        if system.active_list:
            app_state.append_from(
                system.active_list, SpeakerListSerializer, SpeakerListAdded
            )
            order_msg = _get_list_order_msg(system.active_list)
            app_state.append(order_msg)


@receiver(channel_subscribed, sender=AgendaItemChannel)
def ai_channel_subscribed(
    context: AgendaItem, app_state: AppState, user: AbstractUser, **kw
):
    """Send current state to ai channel.
    - Any lists in this context unless they're active (They're already known in that case)
    - Order of those lists
    """
    lists_qs = context.speaker_lists.filter(active_in_system__isnull=True)
    app_state.append_from_queryset(lists_qs, SpeakerListSerializer, SpeakerListAdded)
    for sl in lists_qs:
        msg = _get_list_order_msg(sl)
        app_state.append(msg)
