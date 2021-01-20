from __future__ import annotations

from typing import Counter

from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel, validator

from voteit.messaging.decorators import incoming
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.abcs import PollMethod
from voteit.poll.messages import AddVote, ChangeVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import GenericVoteSchema


__all__ = ("Simple",)


YES = "y"
NO = "n"
VOTE_CHOICES = ((YES, _("Yes")), (NO, _("No")))


class SimpleVoteSchema(BaseModel):
    choice: str

    @validator("choice")
    def choice_validator(cls, v):
        if v not in [YES, NO]:
            raise ValueError("Not a valid choice")
        return v


class VoteSchema(GenericVoteSchema):
    vote: SimpleVoteSchema


@incoming
class AddSimpleVote(AddVote):
    name = "simple_vote.add"
    schema = VoteSchema
    data: VoteSchema


@incoming
class ChangeSimpleVote(ChangeVote):
    name = "simple_vote.change"
    schema = VoteSchema
    data: VoteSchema


class SimplePollResult(BaseModel):
    yes: int
    no: int


@poll_methods
class Simple(PollMethod):
    """ This poll method is a simple approve / deny,
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
        data = self.result_schema(yes=counter[YES], no=counter[NO])
        self.poll.result = data
        return data

    def start_check(self):
        if self.poll.proposals.count() != 1:
            raise InvalidProposalCount("Must be exactly one")
