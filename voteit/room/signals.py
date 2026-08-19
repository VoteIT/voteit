from __future__ import annotations
from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver
from voteit.messaging.signals import channel_subscribed

from voteit.core.decorators import disable_on_raw_save
from voteit.meeting.channels import MeetingChannel
from voteit.room.channels import RoomChannel
from voteit.room.messages import RoomChanged
from voteit.room.messages import RoomDeleted
from voteit.room.messages import RoomHighlighted
from voteit.room.models import Room
from voteit.room.rest_api.serializers import RoomSerializer

if TYPE_CHECKING:
    from voteit.messaging.state import AppState
    from voteit.meeting.models import Meeting

#   instance:   The Room
highlighted_proposals_changed = Signal()


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_subscribed(context: Meeting, app_state: AppState, **kw):
    """
    Send rooms
    """
    for item in RoomSerializer(context.rooms.all(), many=True).data:
        app_state.append(RoomChanged(payload=item))


@receiver(channel_subscribed, sender=RoomChannel)
def room_subscribed(context: Room, app_state: AppState, **kw):
    """
    Send highlighted proposals
    """
    app_state.append(
        RoomHighlighted(
            payload={"pk": context.pk, "highlighted": context.highlighted_proposal_pks}
        )
    )


@receiver(post_save, sender=Room)
@disable_on_raw_save
def send_room_updates(*, instance: Room, created: bool, **kwargs):
    meeting_ch = MeetingChannel(instance.meeting_id)
    data = RoomSerializer(instance).data
    if created:
        msg = RoomChanged(payload=data)
    else:
        msg = RoomChanged(payload={**data, "token": instance.token})
    meeting_ch.sync_publish(msg)


@receiver(pre_delete, sender=Room)
def send_room_deleted(*, instance: Room, **kwargs):
    meeting_ch = MeetingChannel(instance.meeting_id)
    msg = RoomDeleted(payload={"pk": instance.pk})
    meeting_ch.sync_publish(msg)


@receiver(highlighted_proposals_changed, sender=Room)
def send_highlighted_proposals(*, instance, **kwargs):
    room_ch = RoomChannel(instance.pk)
    msg = RoomHighlighted(
        payload={
            "pk": instance.pk,
            "highlighted": instance.highlighted_proposal_pks,
            "token": instance.token,
        }
    )
    room_ch.sync_publish(msg)
