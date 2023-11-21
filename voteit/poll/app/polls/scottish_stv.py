from collections import Counter
from decimal import Decimal

from django.utils.translation import gettext as _
from pydantic import validator
from pydantic.main import BaseModel
from stvpoll.abcs import STVPollBase
from stvpoll.scottish_stv import ScottishSTV as _ScottishSTV
from envelope.messages.errors import ValidationErrorMsg

from voteit.messaging.decorators import incoming
from voteit.poll.abcs import PollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.messages import AddVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import AddRankedVoteSchema
from voteit.poll.schemas import PollResult
from voteit.poll.schemas import RankingSchema

__all__ = ("ScottishSTV",)


class ScottishSTVSettings(BaseModel):
    winners: int
    allow_random: bool = True

    @validator("winners")
    def validate_winners(cls, v):
        """This doesn't check attached polls though!"""
        if v < ScottishSTV.min_winners:
            raise ValueError(f"Must have more winners than {ScottishSTV.min_winners}")
        return v

    class Config:
        allow_mutation = False


@incoming
class AddSTVVote(AddVote):
    name = "scottish_stv_vote.add"
    schema = AddRankedVoteSchema
    data: AddRankedVoteSchema


class STVResultRoundSchema(BaseModel):
    method: str
    status: str
    selected: list[int]
    vote_count: list[tuple[int, float]]

    @validator("vote_count", pre=True)
    def convert_vote_count(cls, v):
        """Vote count from STVPoll method looks like this:
        >>> vote_count = {1: 0.0, 2: 2.0}
        >>> result = STVResultRoundSchema.convert_vote_count(vote_count)
        >>> sorted(result, key=lambda x:x[0])
        [(1, 0.0), (2, 2.0)]

        Feeding it the same data again should yield the same result
        >>> result == STVResultRoundSchema.convert_vote_count(vote_count)
        True
        """
        if isinstance(v, dict):
            return list((k, float(v)) for k, v in v.items())
        return v


class STVResultSchema(PollResult):
    approved: list[int] = []
    denied: list[int] = []
    complete: bool
    rounds: list[STVResultRoundSchema]
    randomized: bool
    quota: int
    runtime: float
    empty_ballot_count: int
    random_order: None | list[int]


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
    # Minimum winners set to 1 due to historic reasons,
    # it should be changed to 2 when all V3 instances have migrated.
    min_winners = 1
    min_losers = 1

    def vote_to_str(self, data: RankingSchema) -> str:
        """
        >>> data = RankingSchema(ranking=[1,3,2])
        >>> method = ScottishSTV(None)
        >>> method.vote_to_str(data)
        '1,3,2'
        >>> method.vote_to_str(RankingSchema(ranking=[]))
        ''
        """
        return ",".join([str(x) for x in data.ranking])

    def vote_to_obj(self, text: str) -> RankingSchema:
        """
        >>> method = ScottishSTV(None)
        >>> data = method.vote_to_obj("4,1,3,2")
        >>> data.ranking
        [4, 1, 3, 2]
        >>> data = method.vote_to_obj("")
        >>> data.ranking
        []
        """
        if text:
            ranking = [int(x) for x in text.split(",")]
        else:
            ranking = []
        return self.vote_schema(ranking=ranking)

    def finalize_stv_result(
        self, counter: Counter, poll_counter: STVPollBase
    ) -> STVResultSchema:
        for ballot, count in counter.items():
            ballot_as_list = [int(r) for r in ballot.split(",")]
            poll_counter.add_ballot(ballot_as_list, count)
        result_dict = poll_counter.calculate().as_dict()
        extra_kwargs = {"approved": result_dict["winners"]}
        if result_dict["complete"]:
            extra_kwargs["denied"] = set(result_dict["candidates"]).difference(
                set(result_dict["winners"])
            )
        return STVResultSchema(**extra_kwargs, **result_dict)

    def calculate_result(self, counter: Counter) -> STVResultSchema:
        settings = self.poll.settings
        poll_counter = _ScottishSTV(
            seats=settings.winners,
            candidates=self.poll.proposals.all().values_list("id", flat=True),
            random_in_tiebreaks=settings.allow_random,
        )
        return self.finalize_stv_result(counter, poll_counter)

    def validate_vote(self, msg: AddSTVVote) -> None:
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
                _("The method %(method)s can't have as many winners as proposals")
                % {"method": self.title}
            )
        if winners < self.min_winners:
            raise InvalidProposalCount(
                _("The method %(method)s require at least %(min_winners)d winners")
                % {"method": self.title, "min_winners": self.min_winners}
            )
