from __future__ import annotations


from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver
from voteit.messaging.channels import UserChannel
from voteit.messaging.registry import batch_for
from rest_framework.exceptions import ValidationError

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.signals import after_sm_transition
from voteit.core.signals import before_sm_transition
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import ensure_atomic
from voteit.core.decorators import on_transaction_commit
from voteit.core.messages.role_updates import RolesChanged
from voteit.core.messages.role_updates import RolesRemoved
from voteit.core.role import Role
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import broadcast_meeting
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.signals import archive_meeting
from voteit.meeting.statemachines import MeetingStateMachine
from voteit.room.channels import RoomChannel
from voteit.speaker.collectors import speaker_payloads
from voteit.speaker.messages import SpeakerChanged
from voteit.speaker.messages import SpeakerDeleted
from voteit.speaker.messages import SpeakerListChanged
from voteit.speaker.messages import SpeakerListDeleted
from voteit.speaker.messages import SpeakerSystemChanged
from voteit.speaker.messages import SpeakerSystemDeleted
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles
from voteit.speaker.rest_api.serializers import SpeakerListSerializer
from voteit.speaker.rest_api.serializers import SpeakerListSystemSerializer
from voteit.speaker.rest_api.serializers import SpeakerSerializer

# instance
active_list_changed = Signal()
# instance, sender (class of list method)
list_method_added = Signal()
list_method_removed = Signal()


@receiver(active_list_changed)
@disable_on_raw_save
def notify_active_list_changed(instance: SpeakerListSystem, **kwargs):
    """
    Send notification when active list changed, if there's a new active list
    """
    if instance.active_list_id:
        serializer = SpeakerListSerializer(instance.active_list)
        msg = SpeakerListChanged(payload=serializer.data)
        room_ch = RoomChannel(instance.room_id)
        room_ch.sync_publish(msg)
        # Same builder as the speaker.active_list collector, so this batch and a
        # subscriber's initial state cannot describe a speaker differently. The
        # six keys used to be spelled out here by hand.
        payloads = list(
            speaker_payloads(Speaker.objects.filter(speaker_list=instance.active_list))
        )
        if payloads:
            # Pre-built batch rather than N messages: the whole active list is
            # replaced at once. TransactionBatcher passes an already-batched
            # message straight through.
            room_ch.sync_publish(batch_for(SpeakerChanged)(payload={"items": payloads}))


# System signals
@receiver(post_save, sender=SpeakerListSystem)
@disable_on_raw_save
def notify_changed_speaker_system(instance: SpeakerListSystem, **kw):
    """
    Updates to speaker system, broadcast to everyone in the meeting.
    """
    if instance.meeting_id:
        data = SpeakerListSystemSerializer(instance).data
        broadcast_meeting(instance.meeting_id, SpeakerSystemChanged(payload=data))


@receiver(post_save, sender=Speaker)
@disable_on_raw_save
@on_transaction_commit
def send_speaker_list_with_current_when_changed(
    instance: Speaker, created: bool, update_fields: frozenset[str] | None, **kwargs
):
    started_and_seconds_unmodified = (
        update_fields is not None
        and not update_fields.intersection({"started", "seconds"})
    )
    if created or started_and_seconds_unmodified:
        return
    speaker_list = instance.speaker_list
    if speaker_list.is_active_list:
        room_id = speaker_list.room_id
        data = SpeakerListSerializer(speaker_list).data
        msg = SpeakerListChanged(payload=data)
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
        msg = SpeakerSystemDeleted(payload={"pk": instance.pk})
        broadcast_meeting(instance.meeting_id, msg)
    # Notify in case method needs any other cleanup
    if instance.method_name:
        instance.signal_list_method_removed(force=True)


# List signals
@receiver(post_save, sender=SpeakerList)
@disable_on_raw_save
@on_transaction_commit
def notify_changed_speaker_list(instance: SpeakerList, created=None, **kw):
    """
    Send to the agenda item, or the whole meeting, depending on if it's the active list.
    """
    data = SpeakerListSerializer(instance).data
    msg = SpeakerListChanged(payload=data)
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
        msg = SpeakerListDeleted(payload={"pk": instance.pk})
        ai_channel = AgendaItemChannel(instance.agenda_item_id)
        ai_channel.sync_publish(msg)
    # We don't need to care about deleted to any other channel, since system will indicate that no list is active.


# Speaker signals
@receiver(post_save, sender=Speaker)
@disable_on_raw_save
@on_transaction_commit
def push_speaker_changed(instance: Speaker, **kwargs):
    # Speakers in the queue are sent as order on list - so we don't need to bother about lists that aren't active
    if instance.speaker_list.is_active_list:
        data = SpeakerSerializer(instance).data
        msg = SpeakerChanged(payload=data)
        room_ch = RoomChannel(instance.speaker_list.room_id)
        room_ch.sync_publish(msg, on_commit=False)  # Already post transaction


@receiver(pre_delete, sender=Speaker)
@disable_on_raw_save
def push_speaker_deleted(instance: Speaker, **kwargs):
    if instance.speaker_list.is_active_list:
        msg = SpeakerDeleted(payload={"pk": instance.pk})
        room_ch = RoomChannel(instance.speaker_list.room_id)
        room_ch.sync_publish(msg)


@receiver(before_sm_transition, sender=AgendaItem)
def check_no_active_speaker(instance: AgendaItem, source, target, event, **kwargs):
    if (
        target.value == AgendaItemStateMachine.closed.value
        and Speaker.objects.filter(
            seconds__isnull=True,
            started__isnull=False,
            speaker_list__agenda_item=instance,
        ).exists()
    ):
        raise ValidationError({"transition": ["Finish active speaker first"]})


@receiver(before_sm_transition, sender=Meeting)
def check_no_active_speaker_when_meeting_closes(
    instance: Meeting, source, target, event, **kwargs
):
    if target.value in (
        MeetingStateMachine.closed.value,
        MeetingStateMachine.deleting.value,
    ):
        if speaker := Speaker.objects.filter(
            seconds__isnull=True,
            started__isnull=False,
            speaker_list__meeting=instance,
        ).first():
            raise ValidationError(
                {
                    "transition": [
                        f"Finish active speaker on speaker list {speaker.speaker_list.title} first!"
                    ]
                }
            )


@receiver(after_sm_transition, sender=AgendaItem)
@ensure_atomic
def close_and_deactivate_when_ai_closes(
    instance: AgendaItem, source, target, event, **kw
):
    if target.value == AgendaItemStateMachine.closed.value:
        for speaker_list in (
            instance.speaker_lists.all()
            .select_related("speaker_system")
            .select_for_update()
        ):
            if speaker_list.is_open:
                speaker_list.close()
                speaker_list.save()
            if speaker_list.speaker_system.active_list_id == speaker_list.pk:
                # Don't use cached version here due to select_for_update
                speaker_list.speaker_system.active_list = None
                speaker_list.speaker_system.save()


# Archiving
@receiver(archive_meeting)
def close_and_cleanup(meeting, **kw):
    for system in meeting.speaker_systems.all():
        system.archive()
        system.save()


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
        broadcast_meeting(instance.meeting, msg)
    # FIXME: Duplicate message to user, but we might not send to meeting later on
    # This is a temporary thing
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.sync_publish(msg)


@receiver(roles_added, sender=SpeakerSystemRoles)
@disable_on_raw_save
def push_roles_added(instance: SpeakerSystemRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesChanged(
            payload={
                "roles": roles,
                "pk": instance.context.pk,
                "model": get_model_shortname(instance.context),
                "user_pk": instance.user.pk,
            }
        ),
    )


@receiver(roles_removed, sender=SpeakerSystemRoles)
@disable_on_raw_save
def push_roles_removed(instance: SpeakerSystemRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesRemoved(
            payload={
                "roles": roles,
                "pk": instance.context.pk,
                "model": get_model_shortname(instance.context),
                "user_pk": instance.user.pk,
            }
        ),
    )
