from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.meeting.channels import MeetingChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.room.channels import RoomChannel
from voteit.room.messages import RoomChanged
from voteit.room.messages import RoomHighlighted
from voteit.room.rest_api.serializers import RoomSerializer

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class Rooms(AppStateCollector):
    name = "room.rooms"
    channels = (MeetingChannel,)
    order = 20

    def collect(self, state: AppState) -> None:
        state.add_batch(
            RoomChanged, RoomSerializer(self.context.rooms.all(), many=True).data
        )


@app_state_collectors
class RoomHighlight(AppStateCollector):
    """Which proposals this room is currently showing."""

    name = "room.highlighted"
    channels = (RoomChannel,)
    order = 50

    def collect(self, state: AppState) -> None:
        state.append(
            RoomHighlighted(
                payload={
                    "pk": self.context.pk,
                    "highlighted": self.context.highlighted_proposal_pks,
                }
            )
        )
