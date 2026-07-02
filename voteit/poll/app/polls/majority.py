from __future__ import annotations

from collections import Counter

from django.utils.translation import gettext as _
from pydantic import BaseModel
from pydantic import validator

from rest_framework.exceptions import ValidationError

from voteit.poll.abcs import PollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import PollResult

__all__ = ("Majority",)


class MajorityVoteSchema(BaseModel):
    choice: int

    @validator("choice")
    def validate_choice(cls, v: int):
        """
        >>> MajorityVoteSchema.validate_choice(1)
        1

        >>> MajorityVoteSchema.validate_choice(0)
        Traceback (most recent call last):
        ...
        ValueError: Must be a positive int
        """
        if v < 1:
            raise ValueError("Must be a positive int")
        return v


class ProposalResult(BaseModel):
    proposal: int
    votes: int = 0


class MajorityPollResult(PollResult):
    results: list[ProposalResult]


@poll_methods
class Majority(PollMethod):
    """
    Classic majority poll that we're limiting to two proposals to avoid all
    nasty side-effects from having more than one proposal.
    """

    title = _("Majority")
    name = "majority"
    vote_schema = MajorityVoteSchema
    result_schema = MajorityPollResult

    def vote_to_str(self, data: MajorityVoteSchema) -> str:
        return data.json()

    def vote_to_obj(self, text: str) -> MajorityVoteSchema:
        return self.vote_schema.parse_raw(text)

    def calculate_result(self, counter: Counter) -> MajorityPollResult:
        """
        Set proposals as approved or denied based on choices.
        Equal result means proposal is neither approved nor denied.

        >>> counter = Counter()

        First with no votes

        >>> majority = Majority(object())
        >>> majority.calculate_result(counter)
        MajorityPollResult(approved=[], denied=[], vote_count=None, results=[])

        And let's add some, but still equal result

        >>> counter['{"choice": 1}'] = 5
        >>> counter['{"choice": 2}'] = 5
        >>> majority.calculate_result(counter)
        MajorityPollResult(approved=[], denied=[], vote_count=None, results=[ProposalResult(proposal=1, votes=5), ProposalResult(proposal=2, votes=5)])

        Finally with a winner
        >>> counter['{"choice": 2}'] = 10
        >>> majority.calculate_result(counter)
        MajorityPollResult(approved=[2], denied=[1], vote_count=None, results=[ProposalResult(proposal=1, votes=5), ProposalResult(proposal=2, votes=10)])
        """
        results = []
        for vote_str, count in counter.items():
            vote = self.vote_to_obj(vote_str)
            results.append(ProposalResult(proposal=vote.choice, votes=count))
        results.sort(key=lambda x: x.votes)
        majority_result = MajorityPollResult(results=results)
        res_len = len(results)
        if res_len > 2:  # pragma: no cover
            raise Exception("Counter returned more than 2 distinct vote types")
        if res_len == 1 and results[0].votes:
            pks = set(self.poll.proposals.values_list("pk", flat=True))
            majority_result.approved = [results[0].proposal]
            pks.remove(results[0].proposal)
            majority_result.denied = [pks.pop()]
        elif res_len == 2 and results[0].votes < results[1].votes:
            majority_result.denied = [results[0].proposal]
            majority_result.approved = [results[1].proposal]
        return majority_result

    def start_check(self):
        if self.poll.proposals.count() < 2:
            raise InvalidProposalCount(_("Must have at least 2 proposals"))

    def validate_vote(self, vote: MajorityVoteSchema) -> None:
        if not self.poll.proposals.filter(pk=vote.choice).exists():
            raise ValidationError({"choice": _("Invalid choice")})
