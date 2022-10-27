from typing import Counter

from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel, validator
from stvpoll import Candidate
from stvpoll import ElectionRound
from stvpoll import IncompleteResult
from stvpoll import STVPollBase

from voteit.messaging.decorators import incoming
from voteit.poll.app.polls.scottish_stv import ScottishSTV
from voteit.poll.app.polls.scottish_stv import STVResultSchema
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.messages import AddVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import AddRankedVoteSchema

__all__ = ("IRV",)


def irv_quota(poll: STVPollBase) -> int:
    """Majority should be more than half of the votes."""
    return ((poll.ballot_count + poll.result.empty_ballot_count) // 2) + 1


class IRVPoll(STVPollBase):
    """Alternative vote or Instant-Runoff Voting is a method for selecting a majority winner
    among a set of proposals / candidates using ranked votes.
    """

    def __init__(self, candidates, quota=irv_quota, random_in_tiebreaks=True):
        super().__init__(1, candidates, quota, random_in_tiebreaks)

    def calculate_round(self) -> None:
        # First, check if there is a winner
        winners = [c for c in self.standing_candidates if c.votes >= self.quota]

        if len(winners) == 1:
            winner = winners[0]
            self.select(winner, ElectionRound.SELECTION_METHOD_DIRECT)

        else:
            if len(self.standing_candidates) == 1:
                raise IncompleteResult("No candidate can get majority.")

            loser, method = self.get_candidate(most_votes=False)
            self.select(loser, method, Candidate.EXCLUDED)
            self.transfer_votes(loser)


@incoming
class AddIRVVote(AddVote):
    name = "irv_vote.add"
    schema = AddRankedVoteSchema
    data: AddRankedVoteSchema


class IRVSettings(BaseModel):
    allow_random: bool = True

    class Config:
        allow_mutation = False


@poll_methods
class IRV(ScottishSTV):
    name = "irv"
    title = _("Instant-Runoff Voting")
    settings_schema = IRVSettings
    min_winners = 1
    max_winners = 1
    min_losers = 2

    def calculate_result(self, counter: Counter) -> STVResultSchema:
        settings = self.poll.settings
        poll_counter = IRVPoll(
            candidates=self.poll.proposals.all().values_list("id", flat=True),
            random_in_tiebreaks=settings.allow_random,
        )
        for (ballot, count) in counter.items():
            ballot_as_list = [int(r) for r in ballot.split(",")]
            poll_counter.add_ballot(ballot_as_list, count)
        result_dict = poll_counter.calculate().as_dict()
        result_dict["approved"] = result_dict.pop("winners")
        if result_dict["complete"]:
            result_dict["denied"] = set(result_dict["candidates"]).difference(
                result_dict["approved"]
            )
        return STVResultSchema(**result_dict)

    def start_check(self):
        if self.poll.proposals.count() < 3:
            raise InvalidProposalCount(
                _("The method %(method)s require at least 3 proposals")
                % {"method": self.title}
            )


class RepeatedIRVPoll(STVPollBase):
    """
    Repeats a regular IRVPoll to select multiple winners.
    Heavily discouraged method!
    """

    def __init__(
        self, seats: int, candidates, quota=irv_quota, random_in_tiebreaks=True
    ):
        super().__init__(seats, candidates, quota, random_in_tiebreaks)

    def calculate_round(self) -> None:
        singular_irv = IRVPoll(
            candidates=self.standing_candidates,
            quota=self._quota_function,
            random_in_tiebreaks=self.random_in_tiebreaks,
        )
        for ballot in self.ballots:
            singular_irv.add_ballot(
                [c for c in ballot.preferences if c in self.standing_candidates],
                ballot.count,
            )
        singular_irv.calculate()

        if not singular_irv.result.complete:
            raise IncompleteResult("No more candidates can get majority.")

        elected = singular_irv.result.elected[0]
        winner = next(c for c in self.candidates if c == elected)
        self.select(winner, ElectionRound.SELECTION_METHOD_DIRECT)


@incoming
class AddIRVVote(AddVote):
    name = "repeated_irv_vote.add"
    schema = AddRankedVoteSchema
    data: AddRankedVoteSchema


class RepeatedIRVSettings(BaseModel):
    winners: int
    allow_random: bool = True

    @validator("winners")
    def validate_winners(cls, v):
        """This doesn't check attached polls though!"""
        if v < RepeatedIRV.min_winners:
            raise ValueError(f"Must have at least {RepeatedIRV.min_winners} winners")
        return v

    class Config:
        allow_mutation = False


@poll_methods
class RepeatedIRV(ScottishSTV):
    name = "repeated_irv"
    title = _("Repeated Instant-Runoff Voting")
    settings_schema = RepeatedIRVSettings
    min_winners = 2
    min_losers = 1

    def calculate_result(self, counter: Counter) -> STVResultSchema:
        settings = self.poll.settings
        poll_counter = RepeatedIRVPoll(
            seats=settings.winners,
            candidates=self.poll.proposals.all().values_list("id", flat=True),
            random_in_tiebreaks=settings.allow_random,
        )
        for (ballot, count) in counter.items():
            ballot_as_list = [int(r) for r in ballot.split(",")]
            poll_counter.add_ballot(ballot_as_list, count)
        result_dict = poll_counter.calculate().as_dict()
        result_dict["approved"] = result_dict.pop("winners")
        if result_dict["complete"]:
            result_dict["denied"] = set(result_dict["candidates"]).difference(
                result_dict["approved"]
            )
        return STVResultSchema(**result_dict)

    def start_check(self):
        if self.poll.proposals.count() < 3:
            raise InvalidProposalCount(
                _("The method %(method)s require at least 3 proposals")
                % {"method": self.title}
            )
