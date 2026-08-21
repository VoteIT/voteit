from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from voteit.agenda.channels import AgendaItemChannel
from voteit.core.messages.role_updates import RolesChanged
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import MeetingChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.room.channels import RoomChannel
from voteit.speaker.messages import SpeakerChanged
from voteit.speaker.messages import SpeakerListChanged
from voteit.speaker.messages import SpeakerSystemChanged
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles
from voteit.speaker.rest_api.serializers import SpeakerListSerializer
from voteit.speaker.rest_api.serializers import SpeakerListSystemSerializer
from voteit.speaker.rest_api.serializers import SpeakerSerializer
from voteit.speaker.statemachines import SpeakerSystemStateMachine

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class SpeakerSystems(AppStateCollector):
    name = "speaker.systems"
    channels = (MeetingChannel,)
    order = 30

    def collect(self, state: AppState) -> None:
        state.add_batch(
            SpeakerSystemChanged,
            SpeakerListSystemSerializer(
                self.context.speaker_systems.all(), many=True
            ).data,
        )


@app_state_collectors
class SpeakerSystemRolesCollector(AppStateCollector):
    """The subscriber's own roles within each speaker system."""

    name = "speaker.roles"
    channels = (MeetingChannel,)
    order = 30

    def collect(self, state: AppState) -> None:
        model_shortname = get_model_shortname(SpeakerListSystem)
        state.add_batch(
            RolesChanged,
            [
                {
                    "roles": row["assigned"],
                    "pk": row["context_id"],
                    "model": model_shortname,
                    "user_pk": self.user.pk,
                }
                # context__in stays a subquery, so this is one query even
                # though the systems are also fetched by speaker.systems.
                for row in SpeakerSystemRoles.objects.filter(
                    user=self.user, context__in=self.context.speaker_systems.all()
                ).values("assigned", "context_id")
            ],
        )


@app_state_collectors
class AgendaItemSpeakerLists(AppStateCollector):
    """Lists on this agenda item that belong to an active system.

    FIXME: So... inactive systems... What happens when they get enabled again?
    """

    name = "speaker.lists"
    channels = (AgendaItemChannel,)
    order = 50

    def collect(self, state: AppState) -> None:
        lists_qs = self.context.speaker_lists.filter(
            speaker_system__state=SpeakerSystemStateMachine.active.value
        )
        state.add_batch(
            SpeakerListChanged, SpeakerListSerializer(lists_qs, many=True).data
        )


@app_state_collectors
class ActiveSpeakerList(AppStateCollector):
    """The room's active list and everyone queued on it."""

    name = "speaker.active_list"
    channels = (RoomChannel,)
    order = 50

    def applicable(self) -> bool:
        try:
            return self.context.sls.active_list_id is not None
        except ObjectDoesNotExist:
            # No SpeakerListSystem for this room at all; .sls raises.
            return False

    def collect(self, state: AppState) -> None:
        active_list = self.context.sls.active_list
        qs = Speaker.objects.filter(
            speaker_list__room=self.context, speaker_list=active_list
        ).select_related("speaker_list")
        state.add_batch(SpeakerChanged, SpeakerSerializer(qs, many=True).data)
        state.append(
            SpeakerListChanged(payload=SpeakerListSerializer(active_list).data)
        )
