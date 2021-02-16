from __future__ import annotations

import json
from typing import Counter, Dict, Set, Tuple, Optional, List

from django.utils.translation import gettext_lazy as _
from py3votecore.schulze_method import SchulzeMethod
from pydantic import BaseModel, validator

from voteit.messaging.decorators import incoming
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.abcs import PollMethod
from voteit.poll.messages import AddVote, ChangeVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import GenericVoteSchema, PollResult

__all__ = ("Schulze", "RepeatedSchulze")


class SchulzeVoteSchema(BaseModel):
    # FIXME Will not serialize: https://github.com/django/channels_redis/issues/216
    ranking: List[Tuple[int, int]]


class VoteSchema(GenericVoteSchema):
    vote: SchulzeVoteSchema


@incoming
class AddSchulzeVote(AddVote):
    name = "schulze_vote.add"
    schema = VoteSchema
    data: VoteSchema


@incoming
class ChangeSchulzeVote(ChangeVote):
    name = "schulze_vote.change"
    schema = VoteSchema
    data: VoteSchema


class SchulzePollResult(PollResult):
    pairs: List[Tuple[Tuple[int, int], int]]
    candidates: List[int]
    winner: int
    strong_pairs: List[Tuple[Tuple[int, int], int]]
    tied_winners: Optional[List[int]]


@poll_methods
class Schulze(PollMethod):
    """One-winner method with multiple proposals. Will produce Condorcet winner/looser(s)."""

    title = _("Schulze")
    name = "schulze"
    vote_schema = SchulzeVoteSchema
    result_schema = SchulzePollResult

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

    def schulze_format(self, counter: Counter) -> List[Dict]:
        """ Internal helper to fix expected input."""
        input = []
        for (text, count) in counter.items():
            ballot = self.vote_to_obj(text)
            ranking = dict(ballot.ranking)  # Method needs a dict
            input.append({"count": count, "ballot": ranking})
        return input

    def schulze_to_poll_result(self, data: Dict) -> SchulzePollResult:
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
        data: Dict = method.as_dict()
        res = self.schulze_to_poll_result(data)
        res.approved.append(res.winner)
        res.denied.extend([x for x in res.candidates if x != res.winner])
        return res

    def start_check(self):
        if self.poll.proposals.count() < 3:
            raise InvalidProposalCount("Must be at least 3")


class RepeatedSchulzeResult(PollResult):
    rounds: List[SchulzePollResult] = []
    candidates: List[int]


class RepeatedSchulzeSettingsSchema(BaseModel):
    winners: Optional[int]  # None means all

    @validator("winners")
    def validate_winners(cls, v):
        if v is not None and v < 2:
            raise ValueError("Must be either none or more than 1")
        return v

    class Config:
        allow_mutation = False


@poll_methods
class RepeatedSchulze(Schulze):
    """ Schulze polls that iterate until sufficient number of winners are picked."""

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
        rounds = []
        for i in range(rounds_to_do):
            method = SchulzeMethod(
                input_data, ballot_notation=SchulzeMethod.BALLOT_NOTATION_RATING
            )
            data: Dict = method.as_dict()
            this_round = self.schulze_to_poll_result(data)
            rounds.append(this_round)
            # Eliminate elected
            for item in input_data:
                item["ballot"].pop(this_round.winner, None)
        # Fetch candidates from first round
        result = self.result_schema(rounds=rounds, candidates=rounds[0].candidates)
        # Sorted polls don't approve or deny
        if not sort_props:
            approved = set()
            for round_result in result.rounds:
                approved.add(round_result.winner)
            result.approved.extend(approved)
            denied = set(result.candidates) - approved
            result.denied.extend(denied)
        return result

    def start_check(self):
        super().start_check()
        winners = self.poll.settings.winners
        if winners and self.poll.proposals.count() <= winners:
            raise InvalidProposalCount(
                "Number of winners must be lower than number of proposals. "
                "If you want the proposals sorted, set winner to None"
            )
