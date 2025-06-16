from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver
from django_fsm import TransitionNotAllowed
from django_fsm import post_transition
from django_fsm import pre_transition
from envelope.app.user_channel.channel import UserChannel
from envelope.signals import channel_subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import ensure_atomic
from voteit.core.decorators import on_transaction_commit
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
from voteit.meeting.workflows import MeetingWf
from voteit.room.channels import RoomChannel
from voteit.speaker.messages import SpeakerAdded
from voteit.speaker.messages import SpeakerChanged
from voteit.speaker.messages import SpeakerDeleted
from voteit.speaker.messages import SpeakerListAdded
from voteit.speaker.messages import SpeakerListChanged
from voteit.speaker.messages import SpeakerListDeleted
from voteit.speaker.messages import SpeakerSystemAdded
from voteit.speaker.messages import SpeakerSystemChanged
from voteit.speaker.messages import SpeakerSystemDeleted
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles
from voteit.speaker.rest_api.serializers import SpeakerListSerializer
from voteit.speaker.rest_api.serializers import SpeakerListSystemSerializer
from voteit.speaker.rest_api.serializers import SpeakerSerializer
from voteit.speaker.workflows import SpeakerListWf
from voteit.speaker.workflows import SpeakerSystemWf

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.utils import AppState
    from voteit.room.models import Room

# instance
active_list_changed = Signal()


@receiver(active_list_changed)
@disable_on_raw_save
def notify_active_list_changed(instance: SpeakerListSystem, **kwargs):
    """
    Send notification when active list changed, if there's a new active list
    """
    if instance.active_list_id:
        serializer = SpeakerListSerializer(instance.active_list)
        msg = SpeakerListChanged(**serializer.data)
        room_ch = RoomChannel(instance.room_id)
        room_ch.sync_publish(msg)


# System signals
@receiver(post_save, sender=SpeakerListSystem)
@disable_on_raw_save
def notify_added_or_changed_speaker_system(
    instance: SpeakerListSystem, created=None, **kw
):
    """
    Updates to speaker system, pushed to meeting channel.
    """
    if instance.meeting_id:
        meeting_ch = MeetingChannel(instance.meeting_id)
        if created:
            msg_class = SpeakerSystemAdded
        else:
            msg_class = SpeakerSystemChanged
        data = SpeakerListSystemSerializer(instance).data
        msg = msg_class(**data)
        meeting_ch.sync_publish(msg)


@receiver(post_save, sender=Speaker)
@disable_on_raw_save
@on_transaction_commit
def send_speaker_list_with_current_when_started_or_stopped(instance: Speaker, **kwargs):
    if not instance.started:
        return
    speaker_list = instance.speaker_list
    if speaker_list.is_active_list:
        room_id = speaker_list.room_id
        data = SpeakerListSerializer(speaker_list).data
        msg = SpeakerListChanged(**data)
        for ch in (
            AgendaItemChannel(speaker_list.agenda_item_id),
            RoomChannel(room_id),
        ):
            # Already post transaction so send right away
            ch.sync_publish(msg, on_commit=False)


@receiver(pre_delete, sender=SpeakerListSystem)
def notify_deleted_speaker_system(instance: SpeakerListSystem, **kw):
    """
    Notify meeting that the speaker system is no more. We had a good run dear friends, you will be missed :(
    """
    if instance.meeting_id:
        msg = SpeakerSystemDeleted(pk=instance.pk)
        ch = MeetingChannel(instance.meeting_id)
        ch.sync_publish(msg)


# List signals
@receiver(post_save, sender=SpeakerList)
@disable_on_raw_save
@on_transaction_commit
def notify_added_or_changed_speaker_list(instance: SpeakerList, created=None, **kw):
    """
    Send to Agenda or meeting channel depending on if it's the active list.
    """
    if created:
        msg_class = SpeakerListAdded
    else:
        msg_class = SpeakerListChanged
    data = SpeakerListSerializer(instance).data
    msg = msg_class(**data)
    if instance.agenda_item_id:
        ai_channel = AgendaItemChannel(instance.agenda_item_id)
        ai_channel.sync_publish(msg)
    # Newly created can't be active list
    if not created and instance.is_active_list:
        room_ch = RoomChannel(instance.room_id)
        room_ch.sync_publish(msg)


@receiver(pre_delete, sender=SpeakerList)
@disable_on_raw_save
def notify_deleted_speaker_list(instance: SpeakerList, **kw):
    if instance.agenda_item_id:
        msg = SpeakerListDeleted(pk=instance.pk)
        ai_channel = AgendaItemChannel(instance.agenda_item_id)
        ai_channel.sync_publish(msg)
    # We don't need to care about deleted to any other channel, since system will indicate that no list is active.


# Speaker signals
@receiver(post_save, sender=Speaker)
@disable_on_raw_save
@on_transaction_commit
def push_speaker_added_or_changed(instance: Speaker, created=False, **kwargs):
    # Speakers in the queue are sent as order on list - so we don't need to bother about lists that aren't active
    if instance.speaker_list.is_active_list:
        data = SpeakerSerializer(instance).data
        if created:
            msg = SpeakerAdded(**data)
        else:
            msg = SpeakerChanged(**data)
        room_ch = RoomChannel(instance.speaker_list.room_id)
        room_ch.sync_publish(msg, on_commit=False)  # Already post transaction


@receiver(pre_delete, sender=Speaker)
@disable_on_raw_save
def push_speaker_deleted(instance: Speaker, **kwargs):
    if instance.speaker_list.is_active_list:
        msg = SpeakerDeleted(pk=instance.pk)
        room_ch = RoomChannel(instance.speaker_list.room_id)
        room_ch.sync_publish(msg)


@receiver(pre_transition, sender=AgendaItem)
def check_no_active_speaker(instance: AgendaItem, source: str, target: str, **kwargs):
    if (
        target == AgendaItemWf.CLOSED
        and Speaker.objects.filter(
            seconds__isnull=True,
            started__isnull=False,
            speaker_list__agenda_item=instance,
        ).exists()
    ):
        raise TransitionNotAllowed(
            "Finish active speaker first", object=instance, method="close"
        )


@receiver(pre_transition, sender=Meeting)
def check_no_active_speaker_when_meeting_closes(
    instance: Meeting, source: str, target: str, **kwargs
):
    if target in (MeetingWf.CLOSED, MeetingWf.DELETING):
        if speaker := Speaker.objects.filter(
            seconds__isnull=True,
            started__isnull=False,
            speaker_list__meeting=instance,
        ).first():
            raise TransitionNotAllowed(
                f"Finish active speaker on speaker list {speaker.speaker_list.title} first!",
                object=instance,
                method="close",
            )


@receiver(post_transition, sender=AgendaItem)
@ensure_atomic
def close_and_deactivate_when_ai_closes(
    instance: AgendaItem, source: str, target: str, **kw
):
    if target == AgendaItemWf.CLOSED:
        for speaker_list in (
            instance.speaker_lists.all()
            .select_related("speaker_system")
            .select_for_update()
        ):
            if speaker_list.state == SpeakerListWf.OPEN:
                speaker_list.close()
                speaker_list.save()
            if speaker_list.speaker_system.active_list_id == speaker_list.pk:
                # Don't use cached version here due to select_for_update
                speaker_list.speaker_system.active_list = None
                speaker_list.speaker_system.save()


# Channels
@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send current state to meeting channel.
    - Speaker systems
    - User roles within speaker systems
    """
    systems_qs = context.speaker_systems.all()
    sys_serializer = SpeakerListSystemSerializer(systems_qs, many=True)
    for item in sys_serializer.data:
        app_state.append(SpeakerSystemAdded(**item))
    model_shortname = get_model_shortname(SpeakerListSystem)
    for rdata in SpeakerSystemRoles.objects.filter(
        user=user, context__in=systems_qs
    ).values("assigned", "context_id"):
        msg = RolesAdded(
            roles=rdata["assigned"],
            pk=rdata["context_id"],
            model=model_shortname,
            user_pk=user.pk,
        )
        app_state.append(msg)


@receiver(channel_subscribed, sender=RoomChannel)
def send_active_speaker_list_speakers(context: Room, app_state: AppState, **kwargs):
    try:
        active_list = context.sls.active_list
    except ObjectDoesNotExist:
        return  # sls will raise this
    if active_list:
        qs = Speaker.objects.filter(
            speaker_list__room=context,
            speaker_list=active_list,
        ).select_related("speaker_list")
        speaker_serializer = SpeakerSerializer(qs, many=True)
        for item in speaker_serializer.data:
            app_state.append(SpeakerAdded(**item))
        list_serializer = SpeakerListSerializer(active_list)
        app_state.append(SpeakerListAdded(**list_serializer.data))


@receiver(channel_subscribed, sender=AgendaItemChannel)
def ai_channel_subscribed(
    context: AgendaItem, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send any lists related to this agenda item.
    """
    # FIXME: So... inactive systems... What happens when they get enabled again?
    lists_qs = context.speaker_lists.filter(
        speaker_system__state=SpeakerSystemWf.ACTIVE
    )
    serializer = SpeakerListSerializer(lists_qs, many=True)
    for item in serializer.data:
        app_state.append(SpeakerListAdded(**item))


# Archiving
@receiver(archive_meeting)
def close_and_cleanup(meeting, **kw):
    for system in meeting.speaker_systems.all():
        system.archive()


# Roles
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
            roles=roles,
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )


@receiver(roles_removed, sender=SpeakerSystemRoles)
@disable_on_raw_save
def push_roles_removed(instance: SpeakerSystemRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesRemoved(
            roles=roles,
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )
