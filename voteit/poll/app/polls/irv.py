from typing import Counter

from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel
from pydantic import validator
from stvpoll.abcs import STVPollBase
from stvpoll.irv import IRV as IRVBase
from stvpoll.exceptions import IncompleteResult
from stvpoll.irv import irv_quota
from stvpoll.types import SelectionMethod

from voteit.messaging.decorators import incoming
from voteit.poll.app.polls.scottish_stv import STVResultSchema
from voteit.poll.app.polls.scottish_stv import ScottishSTV
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.messages import AddVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import AddRankedVoteSchema

__all__ = ("IRV",)


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
        poll_counter = IRVBase(
            candidates=self.poll.proposals.all().values_list("id", flat=True),
            random_in_tiebreaks=settings.allow_random,
        )
        return self.finalize_stv_result(counter, poll_counter)

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
        self.random_in_tiebreaks = random_in_tiebreaks
        super().__init__(seats, candidates, quota, random_in_tiebreaks)

    def singular_quota(self, *args):
        return irv_quota(sum(b.count for b in self.ballots), 0)

    def calculate_round(self) -> None:
        singular_irv = IRVBase(
            candidates=self.standing_candidates,
            quota=self.singular_quota,
            random_in_tiebreaks=self.random_in_tiebreaks,
        )
        for ballot in self.ballots:
            singular_irv.add_ballot(
                [c for c in ballot if c in self.standing_candidates],
                ballot.count,
            )
        singular_irv.calculate()

        if not singular_irv.result.complete:
            raise IncompleteResult("No more candidates can get majority.")

        elected = singular_irv.result[0]
        winner = next(c for c in self.candidates if c == elected)
        self.elect(winner, SelectionMethod.Direct)


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
        return self.finalize_stv_result(counter, poll_counter)

    def start_check(self):
        if self.poll.proposals.count() < 3:
            raise InvalidProposalCount(
                _("The method %(method)s require at least 3 proposals")
                % {"method": self.title}
            )
