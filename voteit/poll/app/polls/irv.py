from typing import Counter

from django.utils.translation import gettext_lazy as _
from envelope.messages.errors import ValidationErrorMsg
from pydantic import BaseModel
from pydantic import PositiveInt
from pydantic import validator
from stvpoll.abcs import STVPollBase
from stvpoll.irv import IRV as IRVBase
from stvpoll.exceptions import IncompleteResult
from stvpoll.irv import irv_quota
from stvpoll.types import SelectionMethod

from voteit.messaging.decorators import incoming
from voteit.poll.app.polls.ranked import AddRankedVote
from voteit.poll.app.polls.scottish_stv import STVResultSchema
from voteit.poll.app.polls.scottish_stv import ScottishSTV
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.registries import poll_methods

__all__ = ("IRV",)


@incoming
class AddIRVVote(AddRankedVote):
    name = "irv_vote.add"


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
class AddRepeatedIRVVote(AddRankedVote):
    name = "repeated_irv_vote.add"


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
    pydantic.error_wrappers.ValidationError:

    >>> s(winners=1)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:

    """

    winners: int  # Validation special
    allow_random: bool = True
    max: None | PositiveInt
    min: None | PositiveInt

    @validator("min", "max", pre=True)
    def no_zeroes(cls, v: int | None):
        if v == 0:
            return None
        return v

    @validator("winners")
    def validate_winners(cls, v):
        """
        This doesn't check attached polls though!
        """
        if v < RepeatedIRV.min_winners:
            raise ValueError(f"Must have at least {RepeatedIRV.min_winners} winners")
        return v

    @validator("min")
    def min_validator(cls, v: int | None, values):
        if v:
            if maxval := values.get("max"):
                if v > maxval:
                    raise ValueError("Min value bigger than max")
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

    def validate_vote(self, msg: AddRankedVote) -> None:
        if (
            self.poll.settings.min
            and len(msg.data.vote.ranking) < self.poll.settings.min
        ):
            raise ValidationErrorMsg.from_message(
                msg,
                msg=str(_("Invalid vote")),
                errors=[
                    {
                        "loc": ("vote.ranking",),
                        "msg": str(_("Too few selected")),
                        "type": "value.error",
                    }
                ],
            )
        if (
            self.poll.settings.max
            and len(msg.data.vote.ranking) > self.poll.settings.max
        ):
            raise ValidationErrorMsg.from_message(
                msg,
                msg=str(_("Invalid vote")),
                errors=[
                    {
                        "loc": ("vote.ranking",),
                        "msg": str(_("Too many selected")),
                        "type": "value.error",
                    }
                ],
            )
        return super().validate_vote(msg)
