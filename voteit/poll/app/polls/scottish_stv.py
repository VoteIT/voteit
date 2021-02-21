from collections import Counter
from typing import List, Dict, Union

from django.utils.translation import gettext as _
from pydantic import validator
from pydantic.main import BaseModel
from stvpoll.scottish_stv import ScottishSTV as _ScottishSTV

from voteit.messaging.decorators import incoming
from voteit.messaging.errors import ValidationErrorMsg
from voteit.poll.abcs import PollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.messages import AddVote, ChangeVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import GenericVoteSchema, PollResult, RankingSchema, RankedVoteSchema

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

    class Config:
        allow_mutation = False


@incoming
class AddSTVVote(AddVote):
    name = "scottish_stv_vote.add"
    schema = RankedVoteSchema
    data: RankedVoteSchema


@incoming
class ChangeSTVVote(ChangeVote):
    name = "scottish_stv_vote.change"
    schema = RankedVoteSchema
    data: RankedVoteSchema


class STVResultSchema(PollResult):
    # winners: List
    # candidates: List
    approved: List[int] = []
    denied: List[int] = []
    complete: bool
    rounds: List[Dict]
    randomized: bool
    quota: int
    runtime: float
    empty_ballot_count: int


@poll_methods
class ScottishSTV(PollMethod):
    """Scottish STV, a ranked proportional vote method for multiple winners.
    proportional = True
    majority_winner = False
    min_losers = 1
    """

    name = "scottish_stv"
    title = _("Scottish STV")
    settings_schema = ScottishSTVSettings
    vote_schema = RankingSchema
    result_schema = STVResultSchema
    min_winners = 2
    min_losers = 1

    def vote_to_str(self, data: RankingSchema) -> str:
        """
        >>> data = RankingSchema(ranking=[1,3,2])
        >>> method = ScottishSTV(None)
        >>> method.vote_to_str(data)
        '1,3,2'
        """
        return ",".join([str(x) for x in data.ranking])

    def vote_to_obj(self, text: str) -> RankingSchema:
        """
        >>> method = ScottishSTV(None)
        >>> data = method.vote_to_obj("4,1,3,2")
        >>> data.ranking
        [4, 1, 3, 2]
        """
        ranking = [int(x) for x in text.split(",")]
        return self.vote_schema(ranking=ranking)

    def calculate_result(self, counter: Counter) -> STVResultSchema:
        settings = self.poll.settings
        poll_counter = _ScottishSTV(
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
        return self.result_schema(**result_dict)

    def validate_vote(self, msg: Union[AddSTVVote, ChangeSTVVote]) -> None:
        matched_pks = set(
            self.poll.proposals.filter(pk__in=msg.data.vote.ranking).values_list(
                "pk", flat=True
            )
        )
        unmatched = set(msg.data.vote.ranking) - matched_pks
        if unmatched:
            raise ValidationErrorMsg.from_message(
                msg,
                msg=_("Invalid vote"),
                errors=[
                    {
                        "loc": ("vote.ranking",),
                        "msg": _(
                            "Invalid choice, the following proposals don't exist: %s"
                        )
                        % ",".join([str(x) for x in unmatched]),
                        "type": "value.error",
                    }
                ],
            )

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
