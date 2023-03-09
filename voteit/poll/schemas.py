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
