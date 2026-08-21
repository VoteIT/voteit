from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.agenda.channels import AgendaItemChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.notes.components import NotesComponent
from voteit.notes.messages import NoteChanged

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class Notes(AppStateCollector):
    """The subscriber's own notes on proposals in this agenda item."""

    name = "notes.notes"
    channels = (AgendaItemChannel,)
    order = 200

    def applicable(self) -> bool:
        return self.context.meeting.component_enabled(NotesComponent.name)

    def collect(self, state: AppState) -> None:
        payloads = []
        for item in self.user.notes.filter(proposal__agenda_item=self.context).values(
            "pk", "proposal_id", "body", "intent", "created", "proposal__agenda_item_id"
        ):
            proposal_id = item.pop("proposal_id")
            agenda_item_id = item.pop("proposal__agenda_item_id")
            payloads.append(
                {
                    **item,
                    "proposal": proposal_id,
                    "user": self.user.id,
                    "meeting": self.context.meeting_id,
                    "agenda_item": agenda_item_id,
                }
            )
        state.add_batch(NoteChanged, payloads)
