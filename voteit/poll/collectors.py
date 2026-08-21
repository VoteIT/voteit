from __future__ import annotations

from typing import TYPE_CHECKING

from sql_util.aggregates import SubqueryCount

from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.poll.messages import ElectoralRegisterChanged
from voteit.poll.messages import GenericVoteResponse
from voteit.poll.messages import PollChanged
from voteit.poll.messages import PollStatus
from voteit.poll.messages import VoteTransferChanged
from voteit.poll.models import Vote
from voteit.poll.rest_api.serializers import ElectoralRegisterSerializer
from voteit.poll.rest_api.serializers import PollDetailSerializer
from voteit.poll.rest_api.serializers import VoteSerializer
from voteit.poll.rest_api.serializers import VoteTransferSerializer

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class Polls(AppStateCollector):
    """Every poll the subscriber is allowed to see.

    Moderators get private polls, polls on private agenda items, and withheld
    results; participants get none of the three.
    """

    name = "poll.polls"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 50

    def collect(self, state: AppState) -> None:
        moderator = isinstance(self.channel, ModeratorsChannel)
        qs = self.context.polls.all()
        if not moderator:
            qs = qs.exclude(state="private").exclude(
                agenda_item__state=AgendaItemStateMachine.private.value
            )
        serializer = PollDetailSerializer(
            qs.prefetch_related("proposals"),
            many=True,
            # {} not None: DRF stores the kwarg as-is and serializer code
            # does self.context.get(...).
            context={"show_withheld": True} if moderator else {},
        )
        state.add_batch(PollChanged, serializer.data)


@app_state_collectors
class PollStatuses(AppStateCollector):
    """Vote counts for the polls that are open right now."""

    name = "poll.status"
    channels = (MeetingChannel,)
    order = 60

    def collect(self, state: AppState) -> None:
        payloads = []
        for poll in (
            self.context.polls.filter(state="ongoing")
            .annotate(voted=SubqueryCount("votes"))
            .select_related("electoral_register")
        ):
            total = (
                len(poll.electoral_register.voter_data)
                if poll.electoral_register
                else 0
            )
            payloads.append({"pk": poll.pk, "voted": poll.voted, "total": total})
        state.add_batch(PollStatus, payloads)


@app_state_collectors
class OwnVotes(AppStateCollector):
    """The subscriber's own votes across the whole meeting.

    Private agenda items do not matter here -- this is the user's own data.

    FIXME: Transmitting every vote is probably not a good idea for large
    meetings. Perhaps change this?
    """

    name = "poll.own_votes"
    channels = (MeetingChannel,)
    order = 200

    def collect(self, state: AppState) -> None:
        qs = Vote.objects.filter(
            poll__in=self.context.polls.all(), user=self.user
        ).prefetch_related("poll")
        state.add_batch(GenericVoteResponse, VoteSerializer(qs, many=True).data)


@app_state_collectors
class LatestElectoralRegister(AppStateCollector):
    name = "poll.electoral_register"
    channels = (MeetingChannel,)
    order = 60

    def collect(self, state: AppState) -> None:
        if self.context.latest_er:
            state.append(
                ElectoralRegisterChanged(
                    payload=ElectoralRegisterSerializer(self.context.latest_er).data
                )
            )


@app_state_collectors
class VoteTransfers(AppStateCollector):
    name = "poll.vote_transfers"
    channels = (MeetingChannel,)
    order = 60

    def applicable(self) -> bool:
        return self.context.vote_transfer_policy is not None

    def collect(self, state: AppState) -> None:
        state.add_batch(
            VoteTransferChanged,
            VoteTransferSerializer(self.context.vote_transfers.all(), many=True).data,
        )
