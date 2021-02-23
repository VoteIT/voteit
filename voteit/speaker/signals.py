from __future__ import annotations

from typing import TYPE_CHECKING, Type

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
from voteit.meeting.signals import archive_meeting
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
from voteit.speaker.rest_api.serializers import (
    SpeakerListSerializer,
    SpeakerListSystemSerializer,
)

if TYPE_CHECKING:
    from voteit.messaging.abcs import BaseOutgoingMessage

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


def _get_list_order_msg(speaker_list: SpeakerList) -> SpeakerListOrder:
    speakers_qs = speaker_list.speakers_qs().prefetch_related("user")
    users = [x.user for x in speakers_qs]
    user_pks = [x.pk for x in users]
    current = speaker_list.current and speaker_list.current.user.pk or None
    return SpeakerListOrder(pk=speaker_list.pk, queue=user_pks, current=current)


def _publish_list_msg(speaker_list: SpeakerList, msg: BaseOutgoingMessage):
    if speaker_list.is_active_list and speaker_list.meeting:
        ch = MeetingChannel.from_instance(speaker_list.meeting)
        ch.publish(msg)
    elif speaker_list.agenda_item is not None:
        ai_ch = AgendaItemChannel.from_instance(speaker_list.agenda_item)
        ai_ch.publish(msg)


@receiver(list_updated)
def push_list_order_change(instance: SpeakerList, **kw):
    """When speakers reorder, send an update of the order.
    This is not transmitted on save for the speaker list,
    since the speaker items are separate.

    Inactive lists are transmitted to each agenda item. Active lists to participants/moderators.
    """
    msg = _get_list_order_msg(instance)
    _publish_list_msg(instance, msg)


@receiver(post_save, sender=SpeakerList)
def notify_added_or_changed_speaker_list(instance: SpeakerList, created=None, **kw):
    """Send to Agenda or meeting channel depending on if it's the active list."""
    if created:
        msg_class = SpeakerListAdded
    else:
        msg_class = SpeakerListChanged
    data = SpeakerListSerializer(instance).data
    msg = msg_class(**data)
    _publish_list_msg(instance, msg)


@receiver(post_delete, sender=SpeakerList)
def notify_deleted_speaker_list(instance: SpeakerList, **kw):
    msg = SpeakerListDeleted(pk=instance.pk)
    _publish_list_msg(instance, msg)


@receiver(post_save, sender=SpeakerListSystem)
def notify_added_or_changed_speaker_system(
    instance: SpeakerListSystem, created=None, **kw
):
    """ Updates to speaker system, pushed to meeting channel."""
    if instance.meeting is not None:
        if created:
            msg_class = SpeakerSystemAdded
        else:
            msg_class = SpeakerSystemChanged
        data = SpeakerListSystemSerializer(instance).data
        msg = msg_class(**data)
        ch = MeetingChannel.from_instance(instance.meeting)
        ch.publish(msg)


@receiver(post_delete, sender=SpeakerListSystem)
def notify_deleted_speaker_system(instance: SpeakerListSystem, **kw):
    """ Notify meeting that the speaker system is no more."""
    if instance.meeting is not None:
        msg = SpeakerSystemDeleted(pk=instance.pk)
        ch = MeetingChannel.from_instance(instance.meeting)
        ch.publish(msg)


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


@receiver(archive_meeting)
def close_and_cleanup(meeting, **kw):
    for system in meeting.speaker_systems.all():
        system.archive()
