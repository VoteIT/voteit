from __future__ import annotations
from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver
from envelope.signals import channel_subscribed

from voteit.core.decorators import disable_on_raw_save
from voteit.meeting.channels import MeetingChannel
from voteit.room.channels import RoomChannel
from voteit.room.messages import RoomAdded
from voteit.room.messages import RoomChanged
from voteit.room.messages import RoomDeleted
from voteit.room.messages import RoomHighlighted
from voteit.room.models import Room
from voteit.room.rest_api.serializers import RoomHighlightedSerializer
from voteit.room.rest_api.serializers import RoomSerializer

if TYPE_CHECKING:
    from envelope.utils import AppState
    from voteit.meeting.models import Meeting

#   instance:   The Room
highlighted_proposals_changed = Signal()


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_subscribed(context: Meeting, app_state: AppState, **kw):
    """
    Send rooms
    """
    app_state.append_from_queryset(context.rooms.all(), RoomSerializer, RoomAdded)


@receiver(channel_subscribed, sender=RoomChannel)
def room_subscribed(context: Room, app_state: AppState, **kw):
    """
    Send highlighted proposals
    """
    app_state.append_from(context, RoomHighlightedSerializer, RoomHighlighted)


@receiver(post_save, sender=Room)
@disable_on_raw_save
def send_room_updates(*, instance: Room, created: bool, **kwargs):
    meeting_ch = MeetingChannel(instance.meeting_id)
    data = RoomSerializer(instance).data
    if created:
        msg = RoomAdded(**data)
    else:
        msg = RoomChanged(**data)
    meeting_ch.sync_publish(msg)


@receiver(pre_delete, sender=Room)
def send_room_deleted(*, instance: Room, **kwargs):
    meeting_ch = MeetingChannel(instance.meeting_id)
    msg = RoomDeleted(pk=instance.pk)
    meeting_ch.sync_publish(msg)


@receiver(highlighted_proposals_changed, sender=Room)
def send_highlighted_proposals(*, instance, **kwargs):
    room_ch = RoomChannel(instance.pk)
    data = RoomHighlightedSerializer(instance).data
    msg = RoomHighlighted(**data)
    room_ch.sync_publish(msg)
