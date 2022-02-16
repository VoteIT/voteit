from __future__ import annotations

import json
from collections import Counter
from typing import List
from typing import Union

from pydantic import BaseModel
from django.utils.translation import gettext as _
from pydantic import validator

from voteit.messaging.decorators import incoming
from voteit.messaging.errors import ValidationErrorMsg
from voteit.poll.abcs import PollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.messages import AddVote
from voteit.poll.messages import ChangeVote
from voteit.poll.registries import poll_methods
from voteit.poll.schemas import GenericAddVoteSchema
from voteit.poll.schemas import GenericExistingVoteSchema
from voteit.poll.schemas import PollResult


class DuttVoteSchema(BaseModel):
    choices: List[int]

    @validator("choices")
    def validate_choices(cls, v: List[int]):
        """
        >>> DuttVoteSchema.validate_choices([1])
        [1]

        >>> DuttVoteSchema.validate_choices([0])
        Traceback (most recent call last):
        ...
        ValueError: Must be a positive int
        """
        for i in v:
            if i < 1:
                raise ValueError("Must be a positive int")
        return v


class DuttSettingsSchema(BaseModel):
    max: int = 0
    min: int = 0


class DuttScore(BaseModel):
    votes: int
    proposal: int


class DuttResultSchema(PollResult):
    results: List[DuttScore]


class AddVoteSchema(GenericAddVoteSchema):
    vote: DuttVoteSchema


@incoming
class AddDuttVote(AddVote):
    name = "dutt.add"
    schema = AddVoteSchema
    data: AddVoteSchema


class ExistingVoteSchema(GenericExistingVoteSchema):
    vote: DuttVoteSchema


@incoming
class ChangeDuttVote(ChangeVote):
    name = "dutt.change"
    schema = ExistingVoteSchema
    data: ExistingVoteSchema


@poll_methods
class Dutt(PollMethod):
    title = "Dutt"
    name = "dutt"
    vote_schema = DuttVoteSchema
    result_schema = DuttResultSchema
    settings_schema = DuttSettingsSchema

    def vote_to_str(self, data: DuttVoteSchema) -> str:
        """
        >>> method = Dutt(None)
        >>> vote = DuttVoteSchema(choices=[1, 2, 3])
        >>> method.vote_to_str(vote)
        '[1, 2, 3]'
        """
        # Sort on proposal id
        items = sorted(data.choices)
        return json.dumps(items)

    def vote_to_obj(self, text: str) -> DuttVoteSchema:
        """
        >>> method = Dutt(None)
        >>> method.vote_to_obj("[1, 2, 3]")
        DuttVoteSchema(choices=[1, 2, 3])
        """
        return self.vote_schema(choices=json.loads(text))

    def reformat_counter(self, counter: Counter) -> Counter:
        """
        Turn counter into choices instead
        >>> from collections import Counter
        >>> counter = Counter()
        >>> counter['[1, 2]'] = 2
        >>> counter['[2, 3]'] = 1
        >>> method = Dutt(None)
        >>> method.reformat_counter(counter)
        Counter({2: 3, 1: 2, 3: 1})
        """
        reformatted = Counter()
        for (k, v) in counter.items():
            ballot = self.vote_to_obj(k)
            for proposal in ballot.choices:
                reformatted[proposal] += v
        return reformatted

    def calculate_result(self, counter: Counter) -> DuttResultSchema:
        """
        >>> from collections import Counter
        >>> counter = Counter()
        >>> counter['[1, 2]'] = 1
        >>> method = Dutt(None)
        >>> method.calculate_result(counter)
        DuttResultSchema(approved=[], denied=[], vote_count=None, results=[DuttScore(votes=1, proposal=1), DuttScore(votes=1, proposal=2)])
        """
        prop_counter = self.reformat_counter(counter)
        results = []
        for (prop, votes) in prop_counter.items():
            results.append(DuttScore(proposal=prop, votes=votes))
        return self.result_schema(results=results)

    def validate_vote(self, msg: Union[AddDuttVote, ChangeDuttVote]) -> None:
        picked_count = len(msg.data.vote.choices)
        settings: DuttSettingsSchema = self.poll.settings
        if settings.min and settings.min > picked_count:
            raise ValidationErrorMsg.from_message(
                msg,
                msg=_("Invalid vote"),
                errors=[
                    {
                        "loc": ("vote.choices",),
                        "msg": _("Too few proposals picked"),
                        "type": "value.error",
                    }
                ],
            )
        if settings.max and settings.max < picked_count:
            raise ValidationErrorMsg.from_message(
                msg,
                msg=_("Invalid vote"),
                errors=[
                    {
                        "loc": ("vote.choices",),
                        "msg": _("Too many proposals picked"),
                        "type": "value.error",
                    }
                ],
            )
        matched_pks = set(
            self.poll.proposals.filter(pk__in=msg.data.vote.choices).values_list(
                "pk", flat=True
            )
        )
        unmatched = set(msg.data.vote.choices) - matched_pks
        if unmatched:
            raise ValidationErrorMsg.from_message(
                msg,
                msg=_("Invalid vote"),
                errors=[
                    {
                        "loc": ("vote.choices",),
                        "msg": _(
                            "Invalid choice, the following proposals don't exist: %s"
                        )
                        % ",".join([str(x) for x in unmatched]),
                        "type": "value.error",
                    }
                ],
            )

    def start_check(self):
        min_count = self.poll.settings.min
        prop_count = self.poll.proposals.count()
        if prop_count < min_count:
            raise InvalidProposalCount("Must be at least %s" % min_count)
        if prop_count < 2:
            raise InvalidProposalCount("Must be at least 2 proposals to vote on")
