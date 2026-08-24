from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.components.messages import MeetingComponentChanged
from voteit.components.rest_api.serializers import MeetingComponentSerializer
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class MeetingComponents(AppStateCollector):
    """Components configured on this meeting, skipping any without an adapter."""

    name = "components.meeting"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 10

    def collect(self, state: AppState) -> None:
        state.add_batch(
            MeetingComponentChanged,
            [
                MeetingComponentSerializer(component).data
                for component in self.context.components.all()
                if component.is_valid
            ],
        )
