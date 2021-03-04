from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Type

from django.db import models
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.core.messages import RolesAdded
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.signals import archive_meeting
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.speaker.messages import SpeakerListAdded
from voteit.speaker.messages import SpeakerListChanged
from voteit.speaker.messages import SpeakerListDeleted
from voteit.speaker.messages import SpeakerListOrder
from voteit.speaker.messages import SpeakerStarted
from voteit.speaker.messages import SpeakerStopped
from voteit.speaker.messages import SpeakerSystemAdded
from voteit.speaker.messages import SpeakerSystemChanged
from voteit.speaker.messages import SpeakerSystemDeleted
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles
from voteit.speaker.rest_api.serializers import SpeakerListSerializer
from voteit.speaker.rest_api.serializers import SpeakerListSystemSerializer

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.messaging.abcs import BaseOutgoingMessage

list_updated = Signal(providing_args=["sender", "instance"])
speaker_started = Signal(providing_args=["sender", "speaker"])
speaker_stopped = Signal(providing_args=["sender", "speaker"])


@receiver(post_save, sender=Speaker)
def set_initial_order(instance: Speaker, created: bool, **kwargs):
    """
    Add order for newly created speakers. If the order attribute is anything but None,
    it means that the speaker is in the queue.
    Is this a new db record? We only care about the newly created for this method.
    """
    if created:
        sl = instance.speaker_list
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
    instance.speaker_list.reorder(force_signal=True)


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


def _publish_active_list_msg(speaker_list: SpeakerList, msg: BaseOutgoingMessage):
    if speaker_list.meeting is not None:
        ch = MeetingChannel.from_instance(speaker_list.meeting)
        ch.publish(msg)


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


@receiver(speaker_started)
def notify_started_speaker(speaker: Speaker, **kwargs):
    msg = SpeakerStarted(
        userid=speaker.user.pk,
        pk=speaker.pk,
        speaker_list=speaker.speaker_list.pk,
        started=speaker.started,
    )
    _publish_active_list_msg(speaker.speaker_list, msg)


@receiver(speaker_stopped)
def notify_stopped_speaker(speaker: Speaker, **kwargs):
    msg = SpeakerStopped(
        userid=speaker.user.pk,
        pk=speaker.pk,
        speaker_list=speaker.speaker_list.pk,
        started=speaker.started,
        seconds=speaker.seconds,
    )
    _publish_active_list_msg(speaker.speaker_list, msg)


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
    - Any ongoing speaker
    - User roles within speaker systems
    """
    systems_qs = context.speaker_systems.all()
    app_state.append_from_queryset(
        systems_qs, SpeakerListSystemSerializer, SpeakerSystemAdded
    )
    for system in systems_qs:
        # Roles
        roles = system.get_roles(user)
        if roles:
            msg = RolesAdded(
                mm=dict(),
                roles=system.roles_to_strings(*roles),
                pk=system.pk,
                model=get_model_shortname(system),
                user_pk=user.pk,
            )
            app_state.append(msg)
        # Active list info
        if system.active_list:
            app_state.append_from(
                system.active_list, SpeakerListSerializer, SpeakerListAdded
            )
            order_msg = _get_list_order_msg(system.active_list)
            app_state.append(order_msg)
            if system.active_list.current is not None:
                speaker = system.active_list.current
                # Append current ongoing speaker
                msg = SpeakerStarted(
                    userid=speaker.user.pk,
                    pk=speaker.pk,
                    speaker_list=system.active_list.pk,
                    started=speaker.started,
                )
                app_state.append(msg)


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


@receiver(roles_added, sender=SpeakerSystemRoles)
def make_speaker_system_users_participants(instance: SpeakerSystemRoles, **kw):
    """
    Whatever role we're adding to speaker system,
    make that user is a participant in the related meeting.
    """
    if instance.meeting is not None:
        instance.meeting.add_roles(instance.user, ROLE_PARTICIPANT)


@receiver(roles_removed, sender=MeetingRoles)
def make_speaker_system_users_participants(instance: MeetingRoles, roles, **kw):
    """
    If someone is removed as a participant from the meeting,
    remove their speaker system roles too.
    """
    if ROLE_PARTICIPANT in roles:
        to_remove = list(SpeakerListSystem.roles_cls.valid_roles.keys())
        for system in instance.meeting.speaker_systems.all():
            system.remove_roles(instance.user, *to_remove)
