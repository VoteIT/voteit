from __future__ import annotations

import json
from typing import Counter

from django.utils.translation import gettext as _
from py3votecore.schulze_method import SchulzeMethod
from pydantic import BaseModel
from pydantic import validator

from envelope.messages.errors import ValidationErrorMsg
from voteit.messaging.decorators import incoming
from voteit.poll.abcs import PollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.messages import AddVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import GenericAddVoteSchema
from voteit.poll.schemas import PollResult

__all__ = ("Schulze", "RepeatedSchulze")


class SchulzeVoteSchema(BaseModel):
    # FIXME Will not serialize: https://github.com/django/channels_redis/issues/216
    ranking: list[tuple[int, int]]


class AddVoteSchema(GenericAddVoteSchema):
    vote: SchulzeVoteSchema


@incoming
class AddSchulzeVote(AddVote):
    name = "schulze_vote.add"
    schema = AddVoteSchema
    data: AddVoteSchema


@incoming
class AddRepeatedSchulzeVote(AddVote):
    name = "repeated_schulze_vote.add"
    schema = AddVoteSchema
    data: AddVoteSchema


class SchulzePollResult(PollResult):
    pairs: list[tuple[tuple[int, int], int]] = []
    candidates: list[int]
    winner: int
    strong_pairs: list[tuple[tuple[int, int], int]] = []
    tied_winners: list[int] | None


class SchulzeSettingsSchema(BaseModel):
    stars: int = 5
    deny_proposal: bool = False

    @validator("stars")
    def validate_stars(cls, v):
        if v > 20:
            raise ValueError("Must be 20 or less")
        if v < 3:
            raise ValueError("Must be 3 or more")
        return v


@poll_methods
class Schulze(PollMethod):
    """
    One-winner method with multiple proposals. Will produce Condorcet winner/looser(s).
    """

    title = _("Schulze")
    name = "schulze"
    vote_schema = SchulzeVoteSchema
    result_schema = SchulzePollResult
    settings_schema = SchulzeSettingsSchema

    def vote_to_str(self, data: SchulzeVoteSchema) -> str:
        """
        >>> method = Schulze(None)
        >>> vote = SchulzeVoteSchema(ranking=[[10, 1], [20, 2], [30, 3]])
        >>> method.vote_to_str(vote)
        '[[10, 1], [20, 2], [30, 3]]'
        """
        # Sort on proposal id
        items = sorted(data.ranking, key=lambda x: x[0])
        return json.dumps(items)

    def vote_to_obj(self, text: str) -> SchulzeVoteSchema:
        """
        >>> method = Schulze(None)
        >>> method.vote_to_obj("[[10, 1], [20, 2], [30, 3]]")
        SchulzeVoteSchema(ranking=[(10, 1), (20, 2), (30, 3)])
        """
        vals = []
        if text:
            vals = json.loads(text)
        return self.vote_schema(ranking=vals)

    def schulze_format(self, counter: Counter) -> list[dict]:
        """
        Internal helper to fix expected input.
        """
        input = []
        for text, count in counter.items():
            ballot = self.vote_to_obj(text)
            ranking = dict(ballot.ranking)  # Method needs a dict
            input.append({"count": count, "ballot": ranking})
        return input

    def schulze_to_poll_result(self, data: dict) -> SchulzePollResult:
        """
        The library we use presents part of the result as dicts with tuple of pairs as key.
        This doesn't work with json, so we have to reformat a bit.
        It looks a bit like this

        >>> data = {'candidates': {1496, 1494, 1495}, 'winner': 1494, \
        'pairs': {(1496, 1494): 0, (1496, 1495): 0, (1494, 1496): 1, (1494, 1495): 1, (1495, 1496): 1, (1495, 1494): 0},\
        'strong_pairs': {(1494, 1496): 1, (1494, 1495): 1, (1495, 1496): 1}}

        With reformat we can now serialize the result
        >>> method = Schulze(None)
        >>> result = method.schulze_to_poll_result(data)
        >>> isinstance(result.json(), str)
        True
        >>> sorted(result.strong_pairs)
        [((1494, 1495), 1), ((1494, 1496), 1), ((1495, 1496), 1)]
        """
        for key in ("pairs", "strong_pairs"):
            data[key] = list(data.get(key, {}).items())
        return SchulzePollResult(**data)

    def calculate_result(self, counter: Counter) -> SchulzePollResult:
        """
        >>> from collections import Counter
        >>> counter = Counter()
        >>> counter['[[10, 1], [20, 2]]'] = 1
        >>> method = Schulze(None)
        >>> result = method.calculate_result(counter)
        >>> result.winner
        20
        >>> set(result.candidates)
        {10, 20}
        """
        input_data = self.schulze_format(counter)
        method = SchulzeMethod(
            input_data, ballot_notation=SchulzeMethod.BALLOT_NOTATION_RATING
        )
        data: dict = method.as_dict()
        res = self.schulze_to_poll_result(data)
        if res.winner == 0:
            # The virtual deny proposal won, so don't make any of the proposals as winners!
            # 0 will be in candidates too here
            res.denied.extend([x for x in res.candidates if x])
        else:
            res.approved.append(res.winner)
            res.denied.extend([x for x in res.candidates if x and x != res.winner])
        return res

    def validate_vote(self, msg: AddSchulzeVote) -> None:
        ranked_pks = [x[0] for x in msg.data.vote.ranking]
        matched_pks = set(
            self.poll.proposals.filter(pk__in=ranked_pks).values_list("pk", flat=True)
        )
        if self.poll.settings.deny_proposal:
            matched_pks.add(0)
        unmatched = set(ranked_pks) - matched_pks
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
        required_count = 3
        deny_proposal = self.poll.settings.deny_proposal
        if deny_proposal:
            required_count = 2
        if self.poll.proposals.count() < required_count:
            raise InvalidProposalCount("Must be at least %s" % required_count)


class RepeatedSchulzeResult(PollResult):
    rounds: list[SchulzePollResult] = []
    candidates: list[int]


class RepeatedSchulzeSettingsSchema(SchulzeSettingsSchema):
    winners: int | None  # None means all

    @validator("winners", pre=True)
    def transform_winners(cls, v):
        """
        Serializers will send "" as empty, but we require None here
        """
        if isinstance(v, str) and not v:
            v = None
        return v

    @validator("winners")
    def validate_winners(cls, v):
        if v is not None and v < 2:
            raise ValueError("Must be either none or more than 1")
        return v

    class Config:
        allow_mutation = False


@poll_methods
class RepeatedSchulze(Schulze):
    """
    Schulze polls that iterate until sufficient number of winners are picked.
    """

    title = _("Repeated Schulze")
    name = "repeated_schulze"
    vote_schema = SchulzeVoteSchema
    result_schema = RepeatedSchulzeResult
    settings_schema = RepeatedSchulzeSettingsSchema

    def calculate_result(self, counter: Counter) -> RepeatedSchulzeResult:
        input_data = self.schulze_format(counter)
        sort_props = self.poll.settings.winners is None
        if sort_props:
            rounds_to_do = self.poll.proposals.count()
        else:
            rounds_to_do = self.poll.settings.winners
        deny_proposal = self.poll.settings.deny_proposal
        rounds = []
        for i in range(rounds_to_do):
            method = SchulzeMethod(
                input_data, ballot_notation=SchulzeMethod.BALLOT_NOTATION_RATING
            )
            data: dict = method.as_dict()
            this_round = self.schulze_to_poll_result(data)
            rounds.append(this_round)
            # Eliminate elected
            for item in input_data:
                item["ballot"].pop(this_round.winner, None)
            # Should we stop due to deny proposal winning?
            if deny_proposal and this_round.winner == 0:
                break
        # Fetch candidates from first round
        result = self.result_schema(rounds=rounds, candidates=rounds[0].candidates)
        # Sorted polls don't approve or deny
        if not sort_props:
            approved = set()
            for round_result in result.rounds:
                if round_result.winner != 0:
                    # Specific proposals that are deny proposals are still winners
                    approved.add(round_result.winner)
            result.approved.extend(approved)
            denied = set(result.candidates) - approved - {0}
            result.denied.extend(denied)
        return result

    def start_check(self):
        super().start_check()
        winners = self.poll.settings.winners
        # Don't include the deny proposal in this count so this is correct!
        if winners:
            required_count = winners + 1
            if self.poll.settings.deny_proposal:
                required_count -= 1
            if self.poll.proposals.count() < required_count:
                raise InvalidProposalCount(
                    "Number of winners must be lower than number of proposals including the option to deny all. "
                    "If you want the proposals sorted, set winner to None"
                )
