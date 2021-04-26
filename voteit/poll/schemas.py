from typing import Any, List

from pydantic.main import BaseModel


class _GenericVoteSchema(BaseModel):
    vote: Any  # Override this
    abstain: bool = False


class GenericAddVoteSchema(_GenericVoteSchema):
    poll: int  # Poll pk for votes


class GenericExistingVoteSchema(_GenericVoteSchema):
    pk: int  # Vote pk


class AddedVoteSchema(_GenericVoteSchema):
    pk: int
    poll: int


class PollResult(BaseModel):
    approved: List[int] = []
    denied: List[int] = []


class RankingSchema(BaseModel):
    ranking: List[int]  # Validation...?


class AddRankedVoteSchema(GenericAddVoteSchema):
    vote: RankingSchema


class ExistingRankedVoteSchema(GenericExistingVoteSchema):
    vote: RankingSchema
