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
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


# Taken from the serializer rather than repeated, so the two cannot drift. Every
# one is a plain concrete column, which is what makes the .values() below a
# faithful substitute -- and if someone adds a method field to the serializer,
# .values() raises FieldError rather than silently dropping it.
AGENDA_ITEM_FIELDS = tuple(AgendaItemListSerializer.Meta.fields)


@app_state_collectors
class AgendaItems(AppStateCollector):
    """The agenda, minus anything private unless this is the moderator channel.

    Uses ``.values()`` rather than the serializer, for the same reason
    ``proposal.collectors.attach_proposals`` does: it skips building a model
    instance per row entirely. Historically the dominant cost was the
    ``python-statemachine`` instance that ``MachineMixin.__init__`` bound to
    every agenda item -- around 120 kB each, roughly 600x the bytes that item
    contributes to the wire. ``StateMachineModelMixin`` made that binding lazy,
    so what remains is the model and DRF overhead; still worth avoiding here,
    but no longer the order-of-magnitude difference it was. The serializer
    declares nine plain columns and no method fields, so the payloads are
    identical either way; ``test_values_matches_the_serializer`` holds that.
    """

    name = "agenda.items"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 20

    def collect(self, state: AppState) -> None:
        qs = self.context.agenda_items.all()
        if not isinstance(self.channel, ModeratorsChannel):
            qs = qs.exclude(state=AgendaItemStateMachine.private.value)
        state.add_batch(AgendaChanged, qs.values(*AGENDA_ITEM_FIELDS))


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
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 200

    def collect(self, state: AppState) -> None:
        qs = self.context.last_read_set.filter(user=self.user).select_related(
            "agenda_item"
        )
        state.add_batch(LastReadChanged, LastReadSerializer(qs, many=True).data)
