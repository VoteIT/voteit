from __future__ import annotations

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.core.decorators import disable_on_raw_save
from voteit.meeting.channels import broadcast_meeting
from voteit.room.channels import RoomChannel
from voteit.room.messages import RoomChanged
from voteit.room.messages import RoomDeleted
from voteit.room.messages import RoomHighlighted
from voteit.room.models import Room
from voteit.room.rest_api.serializers import RoomSerializer

#   instance:   The Room
highlighted_proposals_changed = Signal()


@receiver(post_save, sender=Room)
@disable_on_raw_save
def send_room_updates(*, instance: Room, created: bool, **kwargs):
    data = RoomSerializer(instance).data
    if created:
        msg = RoomChanged(payload=data)
    else:
        msg = RoomChanged(payload={**data, "token": instance.token})
    broadcast_meeting(instance.meeting_id, msg)


@receiver(pre_delete, sender=Room)
def send_room_deleted(*, instance: Room, **kwargs):
    msg = RoomDeleted(payload={"pk": instance.pk})
    broadcast_meeting(instance.meeting_id, msg)


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
