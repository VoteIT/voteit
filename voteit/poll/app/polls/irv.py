from contextlib import suppress
from typing import Counter

from django.utils.translation import gettext_lazy as _
from pydantic import field_validator, ConfigDict, BaseModel
from pydantic import ValidationInfo
from pydantic import PositiveInt
from rest_framework.exceptions import ValidationError
from stvpoll.base import get_ballots
from stvpoll.base import get_votes
from stvpoll.exceptions import CandidateDoesNotExist
from stvpoll.exceptions import IncompleteResult
from stvpoll.exceptions import STVException
from stvpoll.irv import calculate_irv
from stvpoll.irv import irv_quota
from stvpoll.result import ElectionResult
from stvpoll.types import BallotData
from stvpoll.types import Candidates
from stvpoll.types import SelectionMethod

from voteit.poll.app.polls.scottish_stv import STVResultSchema
from voteit.poll.app.polls.scottish_stv import ScottishSTV
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import RankingSchema

__all__ = ("IRV",)


class IRVSettings(BaseModel):
    allow_random: bool = True
    model_config = ConfigDict(frozen=True)


@poll_methods
class IRV(ScottishSTV):
    name = "irv"
    title = _("Instant-Runoff Voting")
    settings_schema = IRVSettings
    min_winners = 1
    max_winners = 1
    min_losers = 2

    def calculate_result(self, counter: Counter) -> STVResultSchema:
        result = calculate_irv(
            self.candidates(),
            self.ballots_from_counter(counter),
            allow_random=self.poll.settings.allow_random,
        )
        return self.stv_result_from(result)

    def start_check(self):
        if self.poll.proposals.count() < 3:
            raise InvalidProposalCount(
                _("The method %(method)s require at least 3 proposals")
                % {"method": self.title}
            )


def calculate_repeated_irv(
    candidates: Candidates,
    ballots: BallotData,
    winners: int,
    *,
    allow_random: bool = True,
) -> ElectionResult:
    """
    Repeats IRV to select multiple winners. Heavily discouraged method!
    Each round runs a full IRV among the remaining candidates, with the majority
    quota based on all non-empty ballots. Rounds record first preference votes.
    """
    if winners > len(candidates):
        raise STVException("Not enough candidates to fill seats")
    result = ElectionResult(candidates=candidates, seats=winners)
    result.empty_ballot_count, ballots = get_ballots(ballots, candidates)
    # get_ballots only checks the first preference of each ballot
    if any(set(b).difference(candidates) for b in ballots):
        raise CandidateDoesNotExist
    quota = irv_quota(sum(b.count for b in ballots), winners)
    first_preferences = get_votes(ballots, candidates, set(candidates))

    with suppress(IncompleteResult):
        while not result.complete:
            standing = tuple(filter(result.still_standing, candidates))
            singular_result = calculate_irv(
                standing,
                [([c for c in b if c in standing], b.count) for b in ballots],
                allow_random=allow_random,
                quota_method=lambda *_: quota,
            )
            if singular_result.randomized:
                result.set_randomized()
            if not singular_result.complete:
                raise IncompleteResult("No more candidates can get majority.")
            result.select(singular_result[0], first_preferences, SelectionMethod.Direct)
    return result.finalize(quota=quota, tiebreakers=())


class RepeatedIRVSettings(BaseModel):
    """
    >>> s = RepeatedIRVSettings

    >>> s(winners=2).dict(include={'winners'})
    {'winners': 2}

    >>> s(winners=2, max=1, min=1).dict(include={'min', 'max'})
    {'max': 1, 'min': 1}

    >>> s(winners=2, max=0).dict(include={'min', 'max'})
    {'max': None, 'min': None}

    >>> s(winners=2, min=1).dict(include={'min', 'max'})
    {'max': None, 'min': 1}

    >>> s(winners=2, max=1).dict(include={'min', 'max'})
    {'max': 1, 'min': None}

    >>> s(winners=2, max=1, min=2).dict(include={'min', 'max'})
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:

    >>> s(winners=1)
    Traceback (most recent call last):
    ...
    pydantic.ValidationError:

    """

    winners: int  # Validation special
    allow_random: bool = True
    max: None | PositiveInt = None
    min: None | PositiveInt = None

    @field_validator("min", "max", mode="before")
    @classmethod
    def no_zeroes(cls, v: int | None):
        if v == 0:
            return None
        return v

    @field_validator("winners")
    @classmethod
    def validate_winners(cls, v):
        """
        This doesn't check attached polls though!
        """
        if v < RepeatedIRV.min_winners:
            raise ValueError(f"Must have at least {RepeatedIRV.min_winners} winners")
        return v

    @field_validator("min")
    @classmethod
    def min_validator(cls, v: int | None, info: ValidationInfo):
        if v:
            if maxval := info.data.get("max"):
                if v > maxval:
                    raise ValueError("Min value bigger than max")
        return v

    model_config = ConfigDict(frozen=True)


@poll_methods
class RepeatedIRV(ScottishSTV):
    name = "repeated_irv"
    title = _("Repeated Instant-Runoff Voting")
    settings_schema = RepeatedIRVSettings
    min_winners = 2
    min_losers = 1

    def calculate_result(self, counter: Counter) -> STVResultSchema:
        settings = self.poll.settings
        result = calculate_repeated_irv(
            self.candidates(),
            self.ballots_from_counter(counter),
            settings.winners,
            allow_random=settings.allow_random,
        )
        return self.stv_result_from(result)

    def start_check(self):
        prop_count = self.poll.proposals.count()
        if prop_count < 3:
            raise InvalidProposalCount(
                _("The method %(method)s require at least 3 proposals")
                % {"method": self.title}
            )
        if self.poll.settings.min and self.poll.settings.min > prop_count:
            raise InvalidProposalCount(
                "Can't have less proposals than required min rankings"
            )

    def validate_vote(self, vote: RankingSchema) -> None:
        if self.poll.settings.min and len(vote.ranking) < self.poll.settings.min:
            raise ValidationError({"ranking": str(_("Too few selected"))})
        if self.poll.settings.max and len(vote.ranking) > self.poll.settings.max:
            raise ValidationError({"ranking": str(_("Too many selected"))})
        return super().validate_vote(vote)
