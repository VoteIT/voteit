from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.messages import AgendaBodyChanged
from voteit.agenda.messages import AgendaChanged
from voteit.agenda.messages import LastReadChanged
from voteit.agenda.rest_api.serializers import AgendaItemBodySerializer
from voteit.agenda.rest_api.serializers import AgendaItemListSerializer
from voteit.agenda.rest_api.serializers import LastReadSerializer
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class AgendaItems(AppStateCollector):
    """The agenda, minus anything private unless this is the moderator channel."""

    name = "agenda.items"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 20

    def collect(self, state: AppState) -> None:
        qs = self.context.agenda_items.all()
        if not isinstance(self.channel, ModeratorsChannel):
            qs = qs.exclude(state=AgendaItemStateMachine.private.value)
        state.add_batch(AgendaChanged, AgendaItemListSerializer(qs, many=True).data)


@app_state_collectors
class AgendaBody(AppStateCollector):
    """The full body of the one agenda item this channel is about."""

    name = "agenda.body"
    channels = (AgendaItemChannel,)
    order = 10

    def collect(self, state: AppState) -> None:
        state.append(
            AgendaBodyChanged(payload=AgendaItemBodySerializer(self.context).data)
        )


@app_state_collectors
class AgendaLastRead(AppStateCollector):
    """When the user last read each agenda item.

    Covers private items the user has visited too. Harmless: it is their own
    read state, and it tells them nothing about the item.
    """

    name = "agenda.last_read"
    channels = (MeetingChannel,)
    order = 200

    def collect(self, state: AppState) -> None:
        qs = self.context.last_read_set.filter(user=self.user).select_related(
            "agenda_item"
        )
        state.add_batch(LastReadChanged, LastReadSerializer(qs, many=True).data)
