from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.agenda.channels import AgendaItemChannel
from voteit.core.utils import get_model_shortname
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.reactions.messages import ButtonChanged
from voteit.reactions.messages import ReactionCount
from voteit.reactions.messages import UserReactionChanged
from voteit.reactions.rest_api.serializers import ButtonDetailSerializer
from voteit.reactions.rest_api.serializers import ReactionSerializer

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class ReactionButtons(AppStateCollector):
    name = "reactions.buttons"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 40

    def collect(self, state: AppState) -> None:
        state.add_batch(
            ButtonChanged,
            ButtonDetailSerializer(self.context.reaction_buttons.all(), many=True).data,
        )


@app_state_collectors
class ReactionCounts(AppStateCollector):
    """How many reactions each button has on each object in this item."""

    name = "reactions.counts"
    channels = (AgendaItemChannel,)
    order = 60

    def collect(self, state: AppState) -> None:
        payloads = []
        for button in (
            self.context.reactions.values("content_type", "object_id", "button")
            .annotate(count=Count("pk"))
            .order_by()
        ):
            # FIXME: Serializer should handle this
            model = ContentType.objects.get_for_id(button["content_type"]).model_class()
            button["content_type"] = get_model_shortname(model)
            payloads.append(button)
        state.add_batch(ReactionCount, payloads)


@app_state_collectors
class OwnReactions(AppStateCollector):
    """The subscriber's own reactions within this agenda item."""

    name = "reactions.own"
    channels = (AgendaItemChannel,)
    order = 200

    def collect(self, state: AppState) -> None:
        state.add_batch(
            UserReactionChanged,
            ReactionSerializer(
                self.context.reactions.filter(user=self.user), many=True
            ).data,
        )
