from __future__ import annotations

from collections import Counter

from django.utils.translation import gettext_lazy as _
from pydantic import field_validator, BaseModel

from voteit.poll.abcs import PollMethod
from voteit.poll.abcs import vote_json
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import PollResult

__all__ = ("CombinedSimple",)


YES = "yes"
NO = "no"
ABSTAIN = "abstain"
VOTE_CHOICES = ((YES, _("Yes")), (NO, _("No")), (ABSTAIN, _("Abstain")))


class CombinedSimpleVoteSchema(BaseModel):
    yes: list[int] = []
    no: list[int] = []
    abstain: list[int] = []

    @field_validator("yes", "no", "abstain")
    @classmethod
    def order_choices(cls, lst: list[int]):
        return sorted(lst)


class ProposalResult(BaseModel):
    yes: int = 0
    no: int = 0
    abstain: int = 0


class CombinedSimplePollResult(PollResult):
    results: dict[int, ProposalResult]


@poll_methods
class CombinedSimple(PollMethod):
    """This poll method is a simple approve / deny,
    but also the base for all tests that should run against the abstract PollMethod.
    """

    VOTE_CHOICES = VOTE_CHOICES
    title = _("Combined Simple")
    name = "combined_simple"
    vote_schema = CombinedSimpleVoteSchema
    result_schema = CombinedSimplePollResult

    def vote_to_str(self, data: CombinedSimpleVoteSchema) -> str:
        return vote_json(data)

    def vote_to_obj(self, text: str) -> CombinedSimpleVoteSchema:
        return self.vote_schema.model_validate_json(text)

    @staticmethod
    def _count_votes(
        pk: int, votes: list[tuple[CombinedSimpleVoteSchema, int]]
    ) -> Counter:
        count = Counter()
        for vote, ct in votes:
            if pk in getattr(vote, YES):
                count[YES] += ct
            elif pk in getattr(vote, NO):
                count[NO] += ct
            else:
                count[ABSTAIN] += ct
        return count

    def calculate_result(self, counter: Counter) -> CombinedSimplePollResult:
        """Set proposals as approved or denied based on YES or NO votes.
        Equal result means proposal is neither approved nor denied.
        """
        votes = [(self.vote_to_obj(vote), ct) for vote, ct in counter.items()]
        results: dict[int, Counter] = {
            pk: self._count_votes(pk, votes)
            for pk in self.poll.proposals.values_list("pk", flat=True)
        }
        approved: list[int] = [
            pk for pk, counter in results.items() if counter[YES] > counter[NO]
        ]
        denied: list[int] = [
            pk for pk, counter in results.items() if counter[YES] < counter[NO]
        ]
        return CombinedSimplePollResult(
            results=results,
            approved=approved,
            denied=denied,
        )

    def start_check(self):
        if self.poll.proposals.count() == 0:
            raise InvalidProposalCount("Must be att least one")
