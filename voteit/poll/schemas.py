from typing import Any

from django.contrib.auth.models import AbstractUser
from pydantic import field_validator, ConfigDict
from pydantic.main import BaseModel


class _GenericVoteSchema(BaseModel):
    vote: Any = None  # Override this
    abstain: bool = False


class AddedVoteSchema(_GenericVoteSchema):
    pk: int
    poll: int


class PollResult(BaseModel):
    approved: list[int] = []
    denied: list[int] = []
    # Optional, so that it can be populated after method calculation
    vote_count: int | None = None


class RankingSchema(BaseModel):
    ranking: list[int]  # Validation...?


class VoterWeightSchema(BaseModel):
    user: int
    weight: int

    @field_validator("user", mode="before")
    @classmethod
    def transform_user(cls, value):
        if isinstance(value, int):
            return value
        elif isinstance(value, AbstractUser):
            return value.pk
        raise ValueError("Wrong user type")

    @field_validator("weight")
    @classmethod
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

    @field_validator("weights")
    @classmethod
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
    require_manual: bool
    allow_trigger: bool
    allow_poll_er_change: bool
    handles_vote_weight: bool
    handles_active_check: bool
    group_votes_active: bool | None = None
    handles_delegate_to: bool
    vote_transfer_policy: str | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def translate(cls, v):
        if not isinstance(v, str):
            return str(v)
        return v

    model_config = ConfigDict(from_attributes=True)
