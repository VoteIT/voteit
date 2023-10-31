from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from django.db.models.signals import m2m_changed
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from envelope.app.user_channel.channel import UserChannel
from envelope.signals import channel_subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.core.decorators import disable_on_raw_save
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
from voteit.speaker.channels import SpeakerListSystemChannel
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
from voteit.speaker.workflows import SpeakerSystemWf

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.utils import AppState


# System signals
@receiver(post_save, sender=SpeakerListSystem)
@disable_on_raw_save
def notify_added_or_changed_speaker_system(
    instance: SpeakerListSystem, created=None, **kw
):
    """
    Updates to speaker system, pushed to meeting channel.
    """
    if instance.meeting is not None:
        meeting_ch = MeetingChannel.from_instance(instance.meeting)
        if created:
            msg_class = SpeakerSystemAdded
        else:
            msg_class = SpeakerSystemChanged
        data = SpeakerListSystemSerializer(instance).data
        msg = msg_class(**data)
        meeting_ch.sync_publish(msg)
        # If there's an active list, push that list too
        if instance.active_list is not None:
            list_data = SpeakerListSerializer(instance.active_list).data
            list_msg = SpeakerListChanged(data=list_data)
            meeting_ch.sync_publish(list_msg)


@receiver(pre_delete, sender=SpeakerListSystem)
def notify_deleted_speaker_system(instance: SpeakerListSystem, **kw):
    """
    Notify meeting that the speaker system is no more. We had a good run dear friends, you will be missed :(
    """
    if instance.meeting is not None:
        msg = SpeakerSystemDeleted(pk=instance.pk)
        ch = MeetingChannel.from_instance(instance.meeting)
        ch.sync_publish(msg)


# List signals
@receiver(post_save, sender=SpeakerList)
@disable_on_raw_save
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
    with suppress(AgendaItem.DoesNotExist):
        if instance.agenda_item:
            ai_channel = AgendaItemChannel.from_instance(instance.agenda_item)
            ai_channel.sync_publish(msg)
    with suppress(SpeakerListSystem.DoesNotExist):
        if instance.is_active_list:
            sls_channel = SpeakerListSystemChannel.from_instance(
                instance.speaker_system
            )
            sls_channel.sync_publish(msg)


@receiver(pre_delete, sender=SpeakerList)
@disable_on_raw_save
def notify_deleted_speaker_list(instance: SpeakerList, **kw):
    """
    We'll send deleted speaker lists to the meeting so they'll always get picked up.
    """
    if instance.meeting:
        msg = SpeakerListDeleted(pk=instance.pk)
        ch = MeetingChannel.from_instance(instance.meeting)
        ch.sync_publish(msg)


# Speaker signals
@receiver(pre_delete, sender=Speaker)
@disable_on_raw_save
def push_speaker_deleted(instance: Speaker, **kwargs):
    if instance.speaker_list.is_active_list:
        msg = SpeakerDeleted(pk=instance.pk)
        ch = SpeakerListSystemChannel.from_instance(instance.speaker_system)
        ch.sync_publish(msg)


@receiver(post_delete, sender=Speaker)
@disable_on_raw_save
def reorder_when_speaker_deleted(instance: Speaker, **kwargs):
    instance.speaker_list.reorder()


@receiver(post_save, sender=Speaker)
@disable_on_raw_save
@on_transaction_commit
def push_speaker_changed(instance: Speaker, created=False, **kwargs):
    """
    We mostly care about currently speaking, stopped + historic speakers here,
    since other items are part of the speaker list. But since speakers who've started speaking
    and then pushed back to queue via undo will be reset, this should be sent on every change.
    """
    if created:
        # Speakers in the queue are sent as order instead. We only care about started or historic speakers
        return
    if instance.speaker_list.is_active_list:
        if sls_id := instance.speaker_list.speaker_system_id:
            data = SpeakerSerializer(instance).data
            # add extra attr here to include speaker list system
            data["sls"] = sls_id
            msg = SpeakerChanged(data=data)
            ch = SpeakerListSystemChannel(sls_id)
            ch.sync_publish(msg, on_commit=False)  # Already post transaction


@receiver(m2m_changed, sender=Speaker)
def speaker_attached_through_m2m(
    instance, reverse: bool, pk_set: set[int], action: str, **kwargs
):
    if (
        action == "post_add"
        and isinstance(instance, SpeakerList)
        and not pk_set.issubset(instance.order_list)
    ):
        instance.reorder()


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
    app_state.append_from_queryset(
        systems_qs, SpeakerListSystemSerializer, SpeakerSystemAdded
    )
    # FIXME: Annotate instead!
    for system in systems_qs:
        # Roles
        roles = system.get_roles(user)
        if roles:
            msg = RolesAdded(
                roles=roles,
                pk=system.pk,
                model=get_model_shortname(system),
                user_pk=user.pk,
            )
            app_state.append(msg)


@receiver(channel_subscribed, sender=SpeakerListSystemChannel)
def list_system_channel_subscribed(
    context: SpeakerListSystem, app_state: AppState, **kw
):
    if active_list := context.active_list:
        data = SpeakerListSerializer(active_list).data
        app_state.append(SpeakerListAdded(data=data))
        # This is for historic speakers
        for speaker in active_list.started_or_historic_speakers().values(
            "pk", "user", "speaker_list", "started", "seconds"
        ):
            # Inject sls as well
            app_state.append(SpeakerAdded(data={"sls": context.pk, **speaker}))


@receiver(channel_subscribed, sender=AgendaItemChannel)
def ai_channel_subscribed(
    context: AgendaItem, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send any lists related to this agenda item.
    """
    lists_qs = context.speaker_lists.filter(
        speaker_system__state=SpeakerSystemWf.ACTIVE
    )
    app_state.append_from_queryset(lists_qs, SpeakerListSerializer, SpeakerListAdded)


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
