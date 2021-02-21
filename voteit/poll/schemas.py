from typing import Any, List

from pydantic.main import BaseModel


class GenericVoteSchema(BaseModel):
    vote: Any  # Override this
    abstain: bool = False
    pk: int  # Poll pk for votes


class PollResult(BaseModel):
    approved: List[int] = []
    denied: List[int] = []


class RankingSchema(BaseModel):
    ranking: List[int]  # Validation...?


class RankedVoteSchema(GenericVoteSchema):
    vote: RankingSchema
