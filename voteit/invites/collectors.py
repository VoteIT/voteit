from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.invites.channels import MeetingInvitesChannel
from voteit.invites.messages import MeetingInviteChanged
from voteit.invites.rest_api.serializers import MeetingInviteSerializer
from voteit.invites.utils import get_invite_adapter_registry
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class MeetingInvites(AppStateCollector):
    """Every invite for this meeting.

    FIXME: We may not want to load all invites unless they're needed.
    """

    name = "invites.invites"
    channels = (MeetingInvitesChannel,)
    order = 50

    def collect(self, state: AppState) -> None:
        reg = get_invite_adapter_registry()
        invites_qs = reg.prep_invites_qs_for_subscribe(self.context.invites.all())
        state.add_batch(
            MeetingInviteChanged,
            MeetingInviteSerializer(invites_qs, many=True).data,
        )
