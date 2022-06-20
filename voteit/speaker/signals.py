from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Type

from django.db import models
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver
from envelope.app.user_channel.channel import UserChannel
from envelope.signals import channel_subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.core.decorators import disable_on_raw_save
from voteit.core.messages.role_updates import RolesAdded
from voteit.core.messages.role_updates import RolesRemoved
from voteit.core.role import Role
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.signals import archive_meeting
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
from voteit.speaker.utils import publish_list_msg

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.utils import AppState
    from envelope.core.message import Message


list_updated = Signal(providing_args=["sender", "instance"])
speaker_started = Signal(providing_args=["sender", "speaker"])
speaker_stopped = Signal(providing_args=["sender", "speaker"])


@receiver(post_save, sender=Speaker)
@disable_on_raw_save
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
    user_pks = list(speaker_list.speakers_qs().values_list("user", flat=True))
    history = list(speaker_list.history_qs().values_list("user", "seconds"))
    current = speaker_list.current and speaker_list.current.user.pk or None
    return SpeakerListOrder(
        pk=speaker_list.pk, queue=user_pks, history=history, current=current
    )


def publish_active_list_msg(speaker_list: SpeakerList, msg: Message):
    """
    Push a message to the currently active list. Just use this if you can assume that this list is active.
    Started/Stopped messages are always sent from the active list for instance.
    """
    if speaker_list.meeting is not None:
        ch = MeetingChannel.from_instance(speaker_list.meeting)
        ch.sync_publish(msg)


@receiver(list_updated)
@disable_on_raw_save
def push_list_order_change(instance: SpeakerList, **kw):
    """When speakers reorder, send an update of the order.
    This is not transmitted on save for the speaker list,
    since the speaker items are separate.

    Inactive lists are transmitted to each agenda item. Active lists to participants/moderators.
    """
    msg = _get_list_order_msg(instance)
    publish_list_msg(instance, msg)


@receiver(post_save, sender=SpeakerList)
@disable_on_raw_save
def notify_added_or_changed_speaker_list(instance: SpeakerList, created=None, **kw):
    """Send to Agenda or meeting channel depending on if it's the active list."""
    if created:
        msg_class = SpeakerListAdded
    else:
        msg_class = SpeakerListChanged
    data = SpeakerListSerializer(instance).data
    msg = msg_class(**data)
    publish_list_msg(instance, msg)


@receiver(speaker_started)
def notify_started_speaker(speaker: Speaker, **kwargs):
    msg = SpeakerStarted(
        user=speaker.user.pk,
        pk=speaker.pk,
        speaker_list=speaker.speaker_list.pk,
        started=speaker.started,
    )
    publish_active_list_msg(speaker.speaker_list, msg)


@receiver(speaker_stopped)
def notify_stopped_speaker(speaker: Speaker, **kwargs):
    _send_speaker_stopped(speaker)


def _send_speaker_stopped(speaker: Speaker):
    msg = SpeakerStopped(
        user=speaker.user.pk,
        pk=speaker.pk,
        speaker_list=speaker.speaker_list.pk,
        started=speaker.started,
        seconds=speaker.seconds,
    )
    publish_active_list_msg(speaker.speaker_list, msg)


@receiver(pre_delete, sender=SpeakerList)
def notify_deleted_speaker_list(instance: SpeakerList, **kw):
    msg = SpeakerListDeleted(pk=instance.pk)
    publish_list_msg(instance, msg)


@receiver(post_save, sender=SpeakerListSystem)
@disable_on_raw_save
def notify_added_or_changed_speaker_system(
    instance: SpeakerListSystem, created=None, **kw
):
    """Updates to speaker system, pushed to meeting channel."""
    if instance.meeting is not None:
        if created:
            msg_class = SpeakerSystemAdded
        else:
            msg_class = SpeakerSystemChanged
        data = SpeakerListSystemSerializer(instance).data
        msg = msg_class(**data)
        ch = MeetingChannel.from_instance(instance.meeting)
        ch.sync_publish(msg)
        # Also push list and order when speaker system changes since it may have changed active list
        active_list = None
        try:
            active_list = instance.active_list
        except SpeakerList.DoesNotExist:
            pass
        if active_list:
            msg_class = SpeakerListChanged
            data = SpeakerListSerializer(instance.active_list).data
            list_msg = msg_class(**data)
            ch.sync_publish(list_msg)
            # And the order
            order_msg = _get_list_order_msg(instance.active_list)
            ch.sync_publish(order_msg)
            # Send last 3 spoken
            for speaker in active_list.history_qs()[:3]:
                _send_speaker_stopped(speaker)


@receiver(pre_delete, sender=SpeakerListSystem)
def notify_deleted_speaker_system(instance: SpeakerListSystem, **kw):
    """Notify meeting that the speaker system is no more."""
    if instance.meeting is not None:
        msg = SpeakerSystemDeleted(pk=instance.pk)
        ch = MeetingChannel.from_instance(instance.meeting)
        ch.sync_publish(msg)


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send current state to meeting channel.
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
                    user=speaker.user.pk,
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
def remove_list_roles_when_participant_removed(instance: MeetingRoles, roles, **kw):
    """
    If someone is removed as a participant from the meeting,
    remove their speaker system roles too.
    """
    if ROLE_PARTICIPANT in roles:
        to_remove = list(SpeakerListSystem.roles_cls.valid_roles.keys())
        for system in instance.meeting.speaker_systems.all():
            system.remove_roles(instance.user, *to_remove)


def _role_msg_publish(instance: SpeakerSystemRoles, msg):
    if isinstance(instance.meeting, Meeting):
        meeting_ch = MeetingChannel.from_instance(instance.meeting)
        meeting_ch.sync_publish(msg)
    # FIXME: Duplicate message to user, but we might not send to meeting later on
    # This is a temporary thing
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.sync_publish(msg)


@receiver(roles_added, sender=SpeakerSystemRoles)
@disable_on_raw_save
def push_roles_added(instance: SpeakerSystemRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesAdded(
            roles=instance.context.roles_to_strings(*roles),
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )


@receiver(roles_removed, sender=SpeakerSystemRoles)
def push_roles_removed(instance: SpeakerSystemRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesRemoved(
            roles=instance.context.roles_to_strings(*roles),
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )
