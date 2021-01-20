from collections import Counter
from decimal import Decimal
from typing import List, Dict

from django.utils.translation import gettext_lazy as _
from pydantic import validator
from pydantic.main import BaseModel
from stvpoll.scottish_stv import ScottishSTV as _ScottishSTV

from voteit.messaging.decorators import incoming
from voteit.poll.abcs import PollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.messages import AddVote, ChangeVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import GenericVoteSchema


__all__ = ("ScottishSTV",)


class ScottishSTVSettings(BaseModel):
    winners: int
    allow_random: bool = True

    @validator("winners")
    def validate_winners(cls, v):
        """ This doesn't check attached polls though!"""
        if v < ScottishSTV.min_winners:
            raise ValueError(f"Must have more winners than {ScottishSTV.min_winners}")
        return v

    # models.BooleanField(
    #     _('Allow random in tiebreaks'), default=True,
    #     help_text=_('Poll may yield incomplete result if random tiebreak is not allowed. '
    #                 'Random tiebreaks can sometimes affect the end result.')
    # )


class STVVoteSchema(BaseModel):
    ranking: List[int]  # Validation...?


class VoteSchema(GenericVoteSchema):
    vote: STVVoteSchema


@incoming
class AddSTVVote(AddVote):
    name = "scottish_stv_vote.add"
    schema = VoteSchema
    data: VoteSchema


@incoming
class ChangeSTVVote(ChangeVote):
    name = "scottish_stv_vote.change"
    schema = VoteSchema
    data: VoteSchema


class STVResultSchema(BaseModel):
    winners: List
    candidates: List
    complete: bool
    rounds: List[Dict]
    randomized: bool
    quota: int
    runtime: Decimal
    empty_ballot_count: int


@poll_methods
class ScottishSTV(PollMethod):
    """ Scottish STV, a ranked proportional vote method for multiple winners.
        proportional = True
        majority_winner = False
        min_losers = 1
    """

    name = "scottish_stv"
    title = _("Scottish STV")
    settings_schema = ScottishSTVSettings
    vote_schema = STVVoteSchema
    result_schema = STVResultSchema
    min_winners = 2
    min_losers = 1

    def vote_to_str(self, data: STVVoteSchema) -> str:
        return ",".join([str(x) for x in data.ranking])

    def vote_to_obj(self, text: str) -> STVVoteSchema:
        ranking = [int(x) for x in text.split(",")]
        return self.vote_schema(ranking=ranking)

    def calculate_result(self, counter: Counter):
        settings = self.poll.settings
        poll_counter = _ScottishSTV(
            seats=settings.winners,
            candidates=self.poll.proposals.all().values_list("id", flat=True),
            random_in_tiebreaks=settings.allow_random,
        )
        for (ballot, count) in counter.items():
            ballot_as_list = [int(r) for r in ballot.split(",")]
            poll_counter.add_ballot(ballot_as_list, count)
        result = self.result_schema(**poll_counter.calculate().as_dict())
        self.poll.result = result
        return result

    def start_check(self):
        winners = self.poll.settings.winners
        if self.poll.proposals.count() < (winners + self.min_losers):
            raise InvalidProposalCount(
                _(
                    "The method %(method)s require at least %(min_losers)d more proposals than winners"
                )
                % {"method": self.title, "min_losers": self.min_losers}
            )
        if winners < self.min_winners:
            raise InvalidProposalCount(
                _("The method %(method)s require at least %(min_winners)d winner(s)")
                % {"method": self.title, "min_winners": self.min_winners}
            )
