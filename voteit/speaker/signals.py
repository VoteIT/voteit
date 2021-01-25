from __future__ import annotations

from typing import TYPE_CHECKING, Type, Optional, Union

from django.db import models
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.channels import MeetingChannel
from voteit.speaker.messages import (
    SpeakerListOrder,
    SpeakerListChanged,
    SpeakerListAdded,
)
from voteit.speaker.models import Speaker, SpeakerList

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
        sl.reorder()


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


@receiver(list_updated)
def push_list_order_change(instance: SpeakerList, **kw):
    """When speakers reorder, send an update of the order.
    This is not transmitted on save for the speaker list,
    since the speaker items are separate.
    """
    speakers_qs = instance.speakers_qs().prefetch_related("user")
    users = [x.user for x in speakers_qs]
    user_pks = [x.pk for x in users]
    channel = _get_list_channel(instance)
    if channel is not None:
        current = instance.current and instance.current.user.pk or None
        order_msg = SpeakerListOrder(pk=instance.pk, queue=user_pks, current=current)
        channel.publish(order_msg)


@receiver(post_save, sender=SpeakerList)
def notify_added_or_changed_speaker_list(instance: SpeakerList, created=None, **kw):
    """Send to Agenda or meeting channel depending on if it's the active list."""
    channel = _get_list_channel(instance)
    if channel is not None:
        if created:
            msg_class = SpeakerListAdded
        else:
            msg_class = SpeakerListChanged
        agenda_item_pk = instance.agenda_item and instance.agenda_item.pk or None
        msg = msg_class(
            title=instance.title,
            pk=instance.pk,
            state=instance.state,
            list_system=instance.list_system.pk,
            agenda_item=agenda_item_pk,
        )
        channel.publish(msg)
