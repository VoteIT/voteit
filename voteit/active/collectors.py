from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.active.messages import ActiveUsers
from voteit.active.utils import active_enabled_for_meeting
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class ActiveUsersCollector(AppStateCollector):
    name = "active.users"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 40

    def applicable(self) -> bool:
        return active_enabled_for_meeting(self.context.meeting)

    def collect(self, state: AppState) -> None:
        state.append(
            ActiveUsers(
                payload={
                    "users": list(
                        self.context.active_users.values_list("user_id", flat=True)
                    ),
                    "meeting": self.context.pk,
                }
            )
        )
