from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.agenda.channels import AgendaItemChannel
from voteit.discussion.messages import DiscussionPostChanged
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.messaging.values import wire_values

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from voteit.messaging.state import AppState


def discussion_post_payloads(qs: QuerySet) -> QuerySet:
    """The ``discussion_post.changed`` payload for every post in ``qs``.

    ``.values()`` rather than DiscussionPostDetailSerializer: the serializer
    declares eight plain columns and no method fields, and the busiest agenda
    item in the dev data holds 281 posts -- 8.3 ms / 664 kB through the
    serializer against 3.7 ms / 501 kB here. The ratio is smaller than for the
    other collectors because the rows are large (post bodies), so the query
    itself is a bigger share of the cost.

    The field list comes from the serializer, and
    ``test_values_matches_the_serializer`` holds that both routes render the
    identical frame -- the post_save signal still goes through the serializer
    for its single instance.
    """
    return wire_values(DiscussionPostDetailSerializer, qs)


@app_state_collectors
class DiscussionPosts(AppStateCollector):
    name = "discussion.posts"
    channels = (AgendaItemChannel,)
    order = 50

    def collect(self, state: AppState) -> None:
        state.add_batch(
            DiscussionPostChanged,
            discussion_post_payloads(self.context.get_discussions()),
        )
