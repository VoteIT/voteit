from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.participant_number.messages import PNChanged

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class ParticipantNumbers(AppStateCollector):
    name = "participant_number.numbers"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 40

    def applicable(self) -> bool:
        try:
            self.context.pn_system
        except ObjectDoesNotExist:
            return False
        return True

    def collect(self, state: AppState) -> None:
        state.add_batch(
            PNChanged,
            [
                {"meeting": self.context.pk, **item}
                for item in self.context.pn_system.numbers.all().values(
                    "number", "user", "pk"
                )
            ],
        )
