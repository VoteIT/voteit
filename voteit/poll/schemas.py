from typing import Any

from django.contrib.auth.models import AbstractUser
from pydantic import validator
from pydantic.main import BaseModel


class _GenericVoteSchema(BaseModel):
    vote: Any  # Override this
    abstain: bool = False


class GenericAddVoteSchema(_GenericVoteSchema):
    poll: int  # Poll pk for votes


class AddedVoteSchema(_GenericVoteSchema):
    pk: int
    poll: int


class PollResult(BaseModel):
    approved: list[int] = []
    denied: list[int] = []
    # Optional, so that it can be populated after method calculation
    vote_count: int | None


class RankingSchema(BaseModel):
    ranking: list[int]  # Validation...?


class AddRankedVoteSchema(GenericAddVoteSchema):
    vote: RankingSchema


class VoterWeightSchema(BaseModel):
    user: int
    weight: int

    @validator("user", pre=True)
    def transform_user(cls, value):
        if isinstance(value, int):
            return value
        elif isinstance(value, AbstractUser):
            return value.pk
        raise ValueError("Wrong user type")

    @validator("weight")
    def validate_weight(cls, v):
        """
        Always a positive int

        >>> VoterWeightSchema.validate_weight(2)
        2
        >>> VoterWeightSchema.validate_weight(1)
        1
        >>> VoterWeightSchema.validate_weight(0)
        Traceback (most recent call last):
        ...
        ValueError: Must be positive int
        """
        if v > 0:
            return v
        raise ValueError("Must be positive int")


class VotersWeightsSchema(BaseModel):
    weights: list[VoterWeightSchema] = ()

    @validator("weights")
    def validate_weights(cls, v):
        """
        >>> VotersWeightsSchema( weights=[{'user': 1, 'weight': 1}])
        VotersWeightsSchema(weights=[VoterWeightSchema(user=1, weight=1)])
        >>> VotersWeightsSchema(weights=[{'user': 1, 'weight': 1}, {'user': 1, 'weight': 1}])
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError: 1 validation error for VotersWeightsSchema
        """
        found = set()
        for vw in v:
            if vw.user in found:
                raise ValueError(f"Duplicate user entry: {vw.user}")
            found.add(vw.user)
        return v


class ElectoralRegistryPolicySchema(BaseModel):
    name: str
    title: str
    description: str = ""
    available: bool
    allow_manual: bool
    allow_trigger: bool
    # handles_personal_vote: bool
    # handles_group_vote: bool
    handles_vote_weight: bool
    handles_active_check: bool
    group_votes_active: bool | None

    @validator("title", "description", pre=True)
    def translate(cls, v):
        if not isinstance(v, str):
            return str(v)
        return v

    class Config:
        orm_mode = True
