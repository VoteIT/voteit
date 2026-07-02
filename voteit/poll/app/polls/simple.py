from __future__ import annotations

from typing import Counter

from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel
from pydantic import validator

from voteit.poll.abcs import PollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import PollResult

__all__ = ("Simple",)


YES = "yes"
NO = "no"
VOTE_CHOICES = ((YES, _("Yes")), (NO, _("No")))


class SimpleVoteSchema(BaseModel):
    choice: str

    @validator("choice")
    def choice_validator(cls, v):
        if v not in [YES, NO]:
            raise ValueError("Not a valid choice")
        return v


class SimplePollResult(PollResult):
    yes: int
    no: int


@poll_methods
class Simple(PollMethod):
    """This poll method is a simple approve / deny,
    but also the base for all tests that should run against the abstract PollMethod.
    """

    VOTE_CHOICES = VOTE_CHOICES
    title = _("Simple")
    name = "simple"
    vote_schema = SimpleVoteSchema
    result_schema = SimplePollResult

    def vote_to_str(self, data: SimpleVoteSchema) -> str:
        return data.choice

    def vote_to_obj(self, text: str) -> SimpleVoteSchema:
        return self.vote_schema(choice=text)

    def calculate_result(self, counter: Counter) -> SimplePollResult:
        """Set proposal as approved or denied based on YES or NO votes.
        Equal result means no approved or denied proposal.
        """
        proposal_pk = self.poll.proposals.get().pk
        result = {
            YES: counter[YES],
            NO: counter[NO],
        }
        if counter[YES] > counter[NO]:
            result["approved"] = [proposal_pk]
        elif counter[YES] < counter[NO]:
            result["denied"] = [proposal_pk]
        return SimplePollResult(**result)

    def start_check(self):
        if self.poll.proposals.count() != 1:
            raise InvalidProposalCount("Must be exactly one")
