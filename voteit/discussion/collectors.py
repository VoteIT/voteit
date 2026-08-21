from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.agenda.channels import AgendaItemChannel
from voteit.discussion.messages import DiscussionPostChanged
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class DiscussionPosts(AppStateCollector):
    name = "discussion.posts"
    channels = (AgendaItemChannel,)
    order = 50

    def collect(self, state: AppState) -> None:
        state.add_batch(
            DiscussionPostChanged,
            DiscussionPostDetailSerializer(
                self.context.get_discussions(), many=True
            ).data,
        )
