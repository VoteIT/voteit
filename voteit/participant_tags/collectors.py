from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.participant_tags.components import GenderTags
from voteit.participant_tags.components import PronounTags
from voteit.participant_tags.messages import AllParticipantTags

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class AllTags(AppStateCollector):
    """Every participant tag in the meeting, inverted to tag -> user pks."""

    name = "participant_tags.all"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 40

    def applicable(self) -> bool:
        # FIXME: These are the only two existing adapters. If we create more,
        # fetch this differently.
        meeting = self.context.meeting
        return meeting.component_enabled(GenderTags.name) or meeting.component_enabled(
            PronounTags.name
        )

    def collect(self, state: AppState) -> None:
        tags = defaultdict(list)
        # Note on order_by, it's mostly for testing
        for row in self.context.participant_tags.order_by("user_id").values(
            "user_id", "tags"
        ):
            for ns, tag_vals in row["tags"].items():
                if isinstance(tag_vals, str):
                    tag_vals = [tag_vals]
                for value in tag_vals:
                    tags[f"{ns}:{value}"].append(row["user_id"])
        state.append(
            AllParticipantTags(payload={"meeting": self.context.pk, "tags": tags})
        )
