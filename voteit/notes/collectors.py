from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from voteit.agenda.channels import AgendaItemChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.notes.components import NotesComponent
from voteit.notes.messages import NoteChanged
from voteit.notes.rest_api.serializers import NoteSerializer

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


# Taken from the serializer rather than repeated, so the two cannot drift.
# ``agenda_item`` is the one field that is not a column on Note --
# NoteSerializer reads it through the proposal, and the queryset does the same
# with an alias, which keeps every other name a plain column. If someone adds a
# method field to the serializer, .values() raises FieldError rather than
# silently dropping it.
NOTE_ANNOTATIONS = {"agenda_item": models.F("proposal__agenda_item_id")}
NOTE_FIELDS = tuple(f for f in NoteSerializer.Meta.fields if f not in NOTE_ANNOTATIONS)


def note_payloads(qs: models.QuerySet) -> models.QuerySet:
    """The ``note.changed`` payload for every note in ``qs``.

    Used by both the collector and the post_save signal, so the two cannot
    disagree about what a note looks like on the wire. ``.values()`` rather
    than NoteSerializer because these payloads are pure columns and the
    serializer is not free: measured at 6.9 ms / 187 kB against 1.3 ms / 67 kB
    for a hundred notes, which is 5.5x the time and 2.8x the memory to produce
    the identical frame. Nothing here binds a state machine -- Note does not use
    StateMachineModelMixin -- so unlike ``agenda.items`` that gap is plain model
    construction and DRF field overhead, and it does not shrink.
    ``test_values_matches_the_serializer`` holds that the frames are equal.
    """
    return qs.values(*NOTE_FIELDS, **NOTE_ANNOTATIONS)


@app_state_collectors
class Notes(AppStateCollector):
    """The subscriber's own notes on proposals in this agenda item."""

    name = "notes.notes"
    channels = (AgendaItemChannel,)
    order = 200

    def applicable(self) -> bool:
        return self.context.meeting.component_enabled(NotesComponent.name)

    def collect(self, state: AppState) -> None:
        qs = self.user.notes.filter(proposal__agenda_item=self.context)
        state.add_batch(NoteChanged, note_payloads(qs))
