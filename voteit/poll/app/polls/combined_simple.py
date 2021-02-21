from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel, validator

from voteit.messaging.decorators import incoming
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.abcs import PollMethod
from voteit.poll.messages import AddVote, ChangeVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import GenericVoteSchema, PollResult

__all__ = ("CombinedSimple",)


YES = "yes"
NO = "no"
ABSTAIN = "abstain"
VOTE_CHOICES = ((YES, _("Yes")), (NO, _("No")), (ABSTAIN, _("Abstain")))


class CombinedSimpleVoteSchema(BaseModel):
    yes: List[int] = []
    no: List[int] = []
    abstain: List[int] = []

    @validator("yes", "no", "abstain")
    def order_choices(cls, lst: List[int]):
        return sorted(lst)


class VoteSchema(GenericVoteSchema):
    vote: CombinedSimpleVoteSchema


@incoming
class AddSimpleVote(AddVote):
    name = "combined_simple_vote.add"
    schema = VoteSchema
    data: VoteSchema


@incoming
class ChangeSimpleVote(ChangeVote):
    name = "combined_simple_vote.change"
    schema = VoteSchema
    data: VoteSchema


class ProposalResult(BaseModel):
    yes: int = 0
    no: int = 0
    abstain: int = 0


class CombinedSimplePollResult(PollResult):
    results: Dict[int, ProposalResult]


@poll_methods
class CombinedSimple(PollMethod):
    """ This poll method is a simple approve / deny,
        but also the base for all tests that should run against the abstract PollMethod.
    """

    VOTE_CHOICES = VOTE_CHOICES
    title = _("Combined Simple")
    name = "combined_simple"
    vote_schema = CombinedSimpleVoteSchema
    result_schema = CombinedSimplePollResult

    def vote_to_str(self, data: CombinedSimpleVoteSchema) -> str:
        return data.json()

    def vote_to_obj(self, text: str) -> CombinedSimpleVoteSchema:
        return self.vote_schema.parse_raw(text)

    @staticmethod
    def _count_votes(pk: int, votes: List[Tuple[CombinedSimpleVoteSchema, int]]) -> Counter:
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
        """ Set proposals as approved or denied based on YES or NO votes.
            Equal result means proposal is neither approved nor denied.
        """
        votes = [(self.vote_to_obj(vote), ct) for vote, ct in counter.items()]
        results: Dict[int, Counter] = {
            pk: self._count_votes(pk, votes) for pk in self.poll.proposals.values_list("pk", flat=True)
        }
        approved: List[int] = [pk for pk, counter in results.items() if counter[YES] > counter[NO]]
        denied: List[int] = [pk for pk, counter in results.items() if counter[YES] < counter[NO]]
        return CombinedSimplePollResult(
            results=results,
            approved=approved,
            denied=denied,
        )

    def start_check(self):
        if self.poll.proposals.count() == 0:
            raise InvalidProposalCount("Must be att least one")
